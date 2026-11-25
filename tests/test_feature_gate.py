import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/feature/scripts"))
import feature_gate as g  # noqa: E402

TEMPLATES = Path(__file__).resolve().parents[1] / "skills/feature/templates"


def test_untouched_templates_fail_their_gates(tmp_path):
    for name in ("01-enrich.md", "03-design.md", "09-report.md"):
        (tmp_path / name).write_text((TEMPLATES / name).read_text())
    assert g.check_enrich(tmp_path)
    assert g.check_design(tmp_path)
    assert g.check_verify(tmp_path)


def test_filled_enrich_passes(tmp_path):
    body = "\n".join(f"## {h}\ntext\n" for h in g.REQUIRED["01-enrich.md"])
    (tmp_path / "01-enrich.md").write_text("# E\n\n" + body)
    assert g.check_enrich(tmp_path) == []


def test_acceptance_rows(tmp_path):
    (tmp_path / "04-acceptance.md").write_text(
        "## Criteria\n| id | what | method | threshold |\n|---|---|---|---|\n"
        "| C1 | x | auto | ≥ 9 of 10 |\n| C2 | y | vibes | 1 |\n\n## Baseline\nno\n"
    )
    assert g.check_acceptance(tmp_path) == ["04-acceptance.md: criterion C2: unknown method vibes"]


def test_qa_check_blocks_threshold_change(tmp_path):
    row = "## Criteria\n| id | w | method | threshold |\n|---|---|---|---|\n| C1 | x | auto | {} |\n\n## Baseline\nno\n"
    (tmp_path / "04-acceptance.md").write_text(row.format("9"))
    assert g.approve_acceptance(tmp_path) == []
    assert g.approve_acceptance(tmp_path)  # second snapshot refused
    (tmp_path / "07-qa-check.md").write_text("ok")
    (tmp_path / "04-acceptance.md").write_text(row.format("5"))
    assert any("threshold changed" in p for p in g.check_qa_check(tmp_path))


def test_artifact_paths_strip_line_suffix_and_urls():
    assert g.artifact_paths("`a/b.py:12-30` `http://x/y` `plain`") == ["a/b.py"]


def test_triage_rules_and_file_limit():
    cfg = g.load_config(Path("/nonexistent"))
    cfg["triage"]["rules"] = [{"reason": "contract", "pattern": "^migrations/"}]
    assert g.triage_reasons(["src/a.py"], None, cfg) == []
    assert "contract" in g.triage_reasons(["migrations/1.sql"], None, cfg)[0]
    assert g.triage_reasons(["a", "b", "c", "d"], None, cfg)


def test_code_gate_scope_escalates_and_checks_run(tmp_path):
    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (tmp_path / "a.py").write_text("1\n")
    git("add", ".")
    git("commit", "-m", "init")
    git("switch", "-c", "feature/x")
    folder = tmp_path / "F"
    folder.mkdir()
    (folder / "02-research.md").write_text("## Affected files\n- `a.py` — edit\n")
    assert g.code_start(folder, tmp_path) == []
    (tmp_path / "a.py").write_text("2\n")
    (tmp_path / "other.py").write_text("x\n")
    problems, code = g.check_code(folder, tmp_path)
    assert code == 2 and "other.py" in problems[0]
    (tmp_path / "other.py").unlink()
    (tmp_path / ".feature").mkdir()
    (tmp_path / ".feature/config.toml").write_text('[checks]\ncommands = ["exit 1"]\n')
    problems, code = g.check_code(folder, tmp_path)
    assert code == 1 and "failed" in problems[0]


def test_bare_identifiers_and_placeholders_are_not_paths():
    body = "`CorpusIndex.load` `chat.json` `src/<new_id>.py` `a/*.py` `README.md` `docs/x.md`"
    assert g.artifact_paths(body, slash_only=True) == ["docs/x.md"]


def test_pipe_in_cell_does_not_split_columns():
    row = "| C1 | match `a|b` and x\\|y | auto | ≥ 9 |"
    assert g.table_rows(row) == [["C1", "match `a|b` and x|y", "auto", "≥ 9"]]


def test_dirty_file_edited_later_is_seen_and_third_fail_escalates(tmp_path):
    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (tmp_path / "a.py").write_text("1\n")
    git("add", ".")
    git("commit", "-m", "init")
    git("switch", "-c", "feature/x")
    (tmp_path / "a.py").write_text("dirty before\n")
    folder = tmp_path / "F"
    folder.mkdir()
    (folder / "02-research.md").write_text("## Affected files\n- `a.py` — edit\n")
    assert g.code_start(folder, tmp_path) == []
    problems, code = g.check_code(folder, tmp_path)
    assert code == 1 and "empty diff" in problems[0]
    (tmp_path / "a.py").write_text("edited by agent\n")
    assert g.check_code(folder, tmp_path) == ([], 0)  # no configured commands: passes

    (folder / "STATE.md").write_text("fails: 0\n\n## History\n")
    codes = [g.log_run(folder, "plan", 1, ["x"]) for _ in range(3)]
    assert codes == [1, 1, 2]
    assert g.state_value(folder, "fails") == "3"
    assert (folder / "STATE.md").read_text().count("| plan |") == 3


def test_comment_hints_are_not_paths():
    assert g.artifact_paths("<!-- `path/from/root.md` --> `docs/x.md`", slash_only=True) == ["docs/x.md"]
