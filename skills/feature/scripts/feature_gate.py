"""Deterministic gates for the /feature workflow.

Usage: feature_gate.py <phase> <feature_dir>   (run from the project root)
Prints one violation per line. Exit code: 0 passed, 1 failed (the agent fixes it),
2 escalation (stop, the user decides).

Project settings live in `.feature/config.toml`; see examples/config.example.toml.
"""

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path.cwd()

REQUIRED: dict[str, list[str]] = {
    "01-enrich.md": ["Task", "What the engineer knows", "Constraints", "Out of scope", "Open questions"],
    "02-research.md": ["Documents read", "Affected files", "Signature dump", "Affected invariants", "Domain type"],
    "03-design.md": ["Decision", "Flow", "What changes", "Invariants", "Rollback", "Alternatives", "Domain type"],
    "04-acceptance.md": ["Criteria", "Baseline"],
    "09-report.md": ["Results", "For the user"],
}

METHODS = {"auto", "manual"}
PLAN_MAX_LINES = 150
PLAN_MAX_CODE_LINES = 5
DEFAULT_CONFIG = {
    "base_branch": "main",
    "checks": {"commands": [], "known_failures": "", "timeout_sec": 600},
    "triage": {"max_short_files": 3, "rules": []},
}

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_BACKTICK = re.compile(r"`([^`\n]+)`")
_LINE_SUFFIX = re.compile(r"(:\d+(-\d+)?|#L\d+(-L?\d+)?)$")


def load_config(root: Path = ROOT) -> dict:
    """Defaults overlaid with `.feature/config.toml` (one level deep)."""
    cfg = {k: dict(v) if isinstance(v, dict) else v for k, v in DEFAULT_CONFIG.items()}
    path = root / ".feature" / "config.toml"
    if path.exists():
        user = tomllib.loads(path.read_text(encoding="utf-8"))
        for key, value in user.items():
            if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                cfg[key].update(value)
            else:
                cfg[key] = value
    return cfg


def section(text: str, heading: str) -> str | None:
    """Body between `## heading` and the next `## `; None when the heading is absent."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.rstrip() == f"## {heading}":
            body = []
            for rest in lines[i + 1 :]:
                if rest.startswith("## "):
                    break
                body.append(rest)
            return "\n".join(body).strip()
    return None


def is_empty(body: str) -> bool:
    return not _COMMENT.sub("", body).strip()


def artifact_paths(body: str) -> list[str]:
    """Backticked paths with `:N`, `:N-M` and `#LN` suffixes removed."""
    paths = []
    for token in _BACKTICK.findall(body):
        token = _LINE_SUFFIX.sub("", token.strip())
        if ("/" in token and "://" not in token) or (" " not in token and re.search(r"\.\w+$", token)):
            paths.append(token)
    return paths


def read(folder: Path, name: str) -> str | None:
    path = folder / name
    return path.read_text(encoding="utf-8-sig") if path.exists() else None


def state_value(folder: Path, key: str) -> str | None:
    for line in (read(folder, "STATE.md") or "").splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return None


def set_state(folder: Path, key: str, value: str) -> None:
    path = folder / "STATE.md"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    for i, line in enumerate(lines):
        if line.startswith(f"{key}:"):
            lines[i] = f"{key}: {value}"
            break
    else:
        lines.insert(0, f"{key}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_sections(folder: Path, name: str, extra: list[str] | None = None) -> tuple[str | None, list[str]]:
    text = read(folder, name)
    if text is None:
        return None, [f"{name}: file missing"]
    problems = []
    for heading in REQUIRED[name] + (extra or []):
        body = section(text, heading)
        if body is None:
            problems.append(f"{name}: missing section «{heading}»")
        elif is_empty(body):
            problems.append(f"{name}: empty section «{heading}»")
    return text, problems


def table_rows(body: str) -> list[list[str]]:
    """Data rows of a markdown table: header and separator rows dropped."""
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0] == "id" or set("".join(cells)) <= set("-: "):
            continue
        rows.append(cells)
    return rows


def criteria(folder: Path, name: str = "04-acceptance.md") -> list[list[str]]:
    return table_rows(section(read(folder, name) or "", "Criteria") or "")


def check_enrich(folder: Path) -> list[str]:
    return check_sections(folder, "01-enrich.md")[1]


def check_research(folder: Path) -> list[str]:
    extra = ["Cause"] if state_value(folder, "kind") == "bug" else []
    text, problems = check_sections(folder, "02-research.md", extra)
    if text is None:
        return problems
    for line in (section(text, "Affected files") or "").splitlines():
        if "edit" in line:
            problems += [f"02-research.md: file not in repo: {p}" for p in artifact_paths(line) if not (ROOT / p).exists()]
    docs = section(text, "Documents read") or ""
    problems += [f"02-research.md: document not in repo: {p}" for p in artifact_paths(docs) if not (ROOT / p).exists()]
    return problems


def check_design(folder: Path) -> list[str]:
    text, problems = check_sections(folder, "03-design.md")
    if text is not None and "```mermaid" not in (section(text, "Flow") or ""):
        problems.append("03-design.md: «Flow» has no ```mermaid block")
    return problems


def check_acceptance(folder: Path) -> list[str]:
    _, problems = check_sections(folder, "04-acceptance.md")
    rows = criteria(folder)
    if not rows:
        problems.append("04-acceptance.md: «Criteria» has no criteria")
    for cells in rows:
        if len(cells) != 4:
            problems.append(f"04-acceptance.md: criterion {cells[0]}: need 4 columns, got {len(cells)}")
            continue
        cid, _, method, threshold = cells
        if method not in METHODS:
            problems.append(f"04-acceptance.md: criterion {cid}: unknown method {method}")
        if not threshold:
            problems.append(f"04-acceptance.md: criterion {cid}: no threshold")
    return problems


def check_plan(folder: Path) -> list[str]:
    text = read(folder, "05-plan.md")
    if text is None:
        return ["05-plan.md: file missing"]
    text = _COMMENT.sub("", text)  # template hints and their example phase are not the plan
    problems = []
    lines = text.splitlines()
    if len(lines) > PLAN_MAX_LINES:
        problems.append(f"05-plan.md: {len(lines)} lines, limit {PLAN_MAX_LINES}")

    fence_start = None
    for n, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            if fence_start is None:
                fence_start = n
            else:
                size = n - fence_start - 1
                if size > PLAN_MAX_CODE_LINES:
                    problems.append(f"05-plan.md: code block at line {fence_start + 1} is {size} lines, limit {PLAN_MAX_CODE_LINES}")
                fence_start = None

    phases = re.split(r"^### Phase", text, flags=re.M)[1:]
    if not phases:
        problems.append("05-plan.md: no «### Phase N — …»")
    for phase in phases:
        name = phase.splitlines()[0].strip()
        for field in ("Files:", "Done when:", "Depends on:"):
            if field not in phase:
                problems.append(f"05-plan.md: phase {name}: no «{field}»")

    allowed = set(artifact_paths(section(read(folder, "02-research.md") or "", "Affected files") or ""))
    for line in lines:
        if line.startswith("Files:"):
            problems += [f"05-plan.md: {p} is not in research «Affected files»" for p in artifact_paths(line) if p not in allowed]
    return problems


def check_verify(folder: Path) -> list[str]:
    text, problems = check_sections(folder, "09-report.md")
    reported = {cells[0] for cells in table_rows(section(text or "", "Results") or "")}
    problems += [f"09-report.md: no result for criterion {cells[0]}" for cells in criteria(folder) if cells[0] not in reported]
    return problems


class GateError(Exception):
    """A gate could not run (git or tooling failure) — reported as a violation, never a traceback."""


def triage_reasons(files: list[str], research_text: str | None, cfg: dict) -> list[str]:
    """Reasons the short cycle is not enough; an empty list means short is fine."""
    reasons = []
    for rule in cfg["triage"]["rules"]:
        pattern = re.compile(rule["pattern"])
        hits = [f for f in files if pattern.search(f)]
        if hits:
            reasons.append(f"{rule['reason']}: {', '.join(hits)}")
    limit = cfg["triage"]["max_short_files"]
    if len(files) > limit:
        reasons.append(f"{len(files)} files, more than {limit}")
    if research_text is not None:
        cause = section(research_text, "Cause") or ""
        if len(re.findall(r"^### Option", cause, flags=re.M)) > 1:
            reasons.append("the cause has more than one fix option")
        inv = (section(research_text, "Affected invariants") or "").strip().rstrip(".").lower()
        if inv and inv != "none":
            reasons.append("project invariants are affected")
    return reasons


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if result.returncode != 0:
        raise GateError(f"git {' '.join(args)}: {result.stderr.strip() or result.returncode}")
    return result.stdout


def changed_files(base: str, repo: Path = ROOT) -> list[str]:
    """Files changed since the merge-base with `base`: committed, uncommitted, untracked."""
    try:
        merge_base = _git(repo, "merge-base", base, "HEAD").strip()
    except GateError as exc:
        raise GateError(f"no common point with branch {base}: {exc}") from exc

    def names(*args: str) -> set[str]:  # -z: NUL-separated, so a path with spaces stays one path
        return {n for n in _git(repo, *args, "-z").split("\0") if n}

    return sorted(names("diff", "--name-only", merge_base) | names("ls-files", "--others", "--exclude-standard"))


def outside_folder(files: list[str], folder: Path, repo: Path) -> list[str]:
    """Workflow artifacts (the feature folder, .feature/) are not code and never count toward scope."""
    skip = [".feature/"]
    try:
        skip.append(folder.resolve().relative_to(repo.resolve()).as_posix() + "/")
    except ValueError:
        pass
    return [f for f in files if not f.startswith(tuple(skip))]


PREEXISTING = "preexisting.txt"


def preexisting(folder: Path) -> set[str]:
    return set((read(folder, PREEXISTING) or "").splitlines()) - {""}


def code_start(folder: Path, repo: Path = ROOT, cfg: dict | None = None) -> list[str]:
    """Record files already dirty before Code, so the scope check does not blame the agent for them."""
    cfg = cfg or load_config(repo)
    if (folder / PREEXISTING).exists():
        return [f"{PREEXISTING} already taken — a second snapshot would hide the agent's edits"]
    try:
        files = outside_folder(changed_files(cfg["base_branch"], repo), folder, repo)
    except GateError as exc:
        return [str(exc)]
    (folder / PREEXISTING).write_text("".join(f"{f}\n" for f in files), encoding="utf-8")
    return []


def research_files(folder: Path) -> tuple[str | None, list[str]]:
    text = read(folder, "02-research.md")
    return text, artifact_paths(section(text or "", "Affected files") or "")


def run_triage(folder: Path) -> tuple[list[str], int]:
    text, files = research_files(folder)
    if text is None:
        return ["02-research.md: file missing"], 1
    reasons = triage_reasons(files, text, load_config())
    set_state(folder, "cycle", "full" if reasons else "short")
    set_state(folder, "triage", "; ".join(reasons) or "no rule fired")
    return [], 0


FAILED_LINE = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.M)


def run_checks(repo: Path, cfg: dict) -> list[str]:
    """Run every configured command; pytest-style failures listed in known_failures are tolerated."""
    checks = cfg["checks"]
    kf_path = repo / checks["known_failures"] if checks["known_failures"] else None
    known = set(FAILED_LINE.findall(kf_path.read_text(encoding="utf-8"))) if kf_path and kf_path.exists() else set()
    problems = []
    for cmd in checks["commands"]:
        try:
            run = subprocess.run(cmd, shell=True, cwd=repo, capture_output=True, text=True, timeout=checks["timeout_sec"])
        except subprocess.TimeoutExpired:
            problems.append(f"`{cmd}`: timeout after {checks['timeout_sec']} s")
            continue
        if run.returncode == 0:
            continue
        out = run.stdout + run.stderr
        failed = set(FAILED_LINE.findall(out))
        if failed and failed <= known:
            continue
        new = sorted(failed - known)
        problems.append(f"`{cmd}` failed (exit {run.returncode})" + (f"; new failures: {', '.join(new)}" if new else ""))
        problems += out.splitlines()[-20:]
    return problems


def check_code(folder: Path, repo: Path = ROOT) -> tuple[list[str], int]:
    """Scope and cycle escalations first (exit 2), then configured commands (exit 1)."""
    cfg = load_config(repo)
    try:
        files = changed_files(cfg["base_branch"], repo)
    except GateError as exc:
        return [str(exc)], 1
    if not (folder / PREEXISTING).exists():
        return [f"no {PREEXISTING}: run code-start at the beginning of Code"], 1
    # ponytail: an agent edit to a file that was already dirty hides here; start Code on a clean tree
    files = [f for f in outside_folder(files, folder, repo) if f not in preexisting(folder)]
    if not files:
        return ["empty diff: the agent has changed nothing yet"], 1

    _, allowed = research_files(folder)
    outside = [f"ESCALATE: {f} is outside research «Affected files»" for f in files if f not in allowed]
    if outside:
        return outside, 2
    if state_value(folder, "cycle") == "short":
        reasons = triage_reasons(files, None, cfg)
        if reasons:
            return [f"ESCALATE: short cycle, but the diff needs the full one: {r}" for r in reasons], 2

    problems = run_checks(repo, cfg)
    return problems, 1 if problems else 0


APPROVED = "04-acceptance.approved.md"


def approve_acceptance(folder: Path) -> list[str]:
    """Snapshot the acceptance plan at the moment the user approves it."""
    text = read(folder, "04-acceptance.md")
    if text is None:
        return ["04-acceptance.md: file missing"]
    if (folder / APPROVED).exists():
        return [f"acceptance already approved ({APPROVED}); a new snapshot only after the user deletes the old one"]
    (folder / APPROVED).write_text(text, encoding="utf-8")
    return []


def check_qa_check(folder: Path) -> list[str]:
    """No approved criterion may disappear or change its threshold; new criteria are allowed."""
    problems = [] if (folder / "07-qa-check.md").exists() else ["07-qa-check.md: file missing"]
    if not (folder / APPROVED).exists():
        return [*problems, f"acceptance not approved: no {APPROVED}"]
    current = {cells[0]: cells for cells in criteria(folder)}
    for cells in criteria(folder, APPROVED):
        cid = cells[0]
        if cid not in current:
            problems.append(f"04-acceptance.md: approved criterion {cid} was removed")
        # ponytail: any threshold edit fails, even a stricter one; parse numbers if that keeps tripping
        elif current[cid][3:4] != cells[3:4]:
            problems.append(f"04-acceptance.md: criterion {cid} threshold changed: {cells[3:4]} → {current[cid][3:4]}")
    return problems


CHECKS = {
    "enrich": check_enrich,
    "research": check_research,
    "design": check_design,
    "acceptance": check_acceptance,
    "plan": check_plan,
    "verify": check_verify,
    "qa-check": check_qa_check,
    "approve-acceptance": approve_acceptance,
    "code-start": code_start,
}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("phase", choices=sorted([*CHECKS, "triage", "code"]))
    parser.add_argument("feature_dir", type=Path)
    args = parser.parse_args(argv)
    if args.phase == "triage":
        problems, code = run_triage(args.feature_dir)
    elif args.phase == "code":
        problems, code = check_code(args.feature_dir)
    else:
        problems = CHECKS[args.phase](args.feature_dir)
        code = 1 if problems else 0
    sys.stdout.writelines(f"{problem}\n" for problem in problems)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
