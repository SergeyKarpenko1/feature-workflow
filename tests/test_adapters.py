import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_generated_judges_are_up_to_date():
    run = subprocess.run([sys.executable, str(ROOT / "scripts/build_adapters.py"), "--check"], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout


def test_codex_agents_have_required_fields_and_no_claude_leftovers():
    files = sorted((ROOT / "adapters/codex/agents").glob("*.toml"))
    assert [f.stem for f in files] == ["arch_judge", "design_judge"]
    for file in files:
        data = tomllib.loads(file.read_text(encoding="utf-8"))
        assert {"name", "description", "developer_instructions"} <= set(data)
        assert data["name"] == file.stem
        assert "<!--" not in data["developer_instructions"]


def test_skill_is_agent_neutral():
    skill = (ROOT / "skills/feature/SKILL.md").read_text(encoding="utf-8")
    assert "CLAUDE_SKILL_DIR" not in skill
    assert "design_judge" in skill and "design-judge" in skill


def test_install_codex_agents_copies_files(tmp_path):
    run = subprocess.run([sys.executable, str(ROOT / "scripts/install_codex_agents.py"), str(tmp_path / "agents")], capture_output=True, text=True)
    assert run.returncode == 0
    assert sorted(p.name for p in (tmp_path / "agents").iterdir()) == ["arch_judge.toml", "design_judge.toml"]
