"""Build per-agent judge definitions from the single source in judges/.

    python3 scripts/build_adapters.py          # write agents/*.md and adapters/codex/agents/*.toml
    python3 scripts/build_adapters.py --check  # exit 1 if the generated files are stale

judges/<name>.md = frontmatter (name, description, claude_tools, optional claude_model) + prompt body.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_COMMENT = re.compile(r"<!--.*?-->\s*", re.S)


def parse(path: Path) -> tuple[dict[str, str], str]:
    _, front, body = path.read_text(encoding="utf-8").split("---", 2)
    meta = dict(line.split(": ", 1) for line in front.strip().splitlines())
    return meta, body.strip() + "\n"


def claude_agent(meta: dict[str, str], body: str) -> str:
    lines = [f"name: {meta['name']}", f"description: {meta['description']}", f"tools: {meta['claude_tools']}"]
    if "claude_model" in meta:
        lines.append(f"model: {meta['claude_model']}")
    return "---\n" + "\n".join(lines) + "\n---\n\n" + body


def codex_agent(meta: dict[str, str], body: str) -> str:
    text = _COMMENT.sub("", body).strip() + "\n"
    assert "'''" not in text, "judge prompt must not contain ''' (TOML literal string)"
    name = meta["name"].replace("-", "_")
    return f"name = \"{name}\"\ndescription = \"{meta['description']}\"\ndeveloper_instructions = '''\n{text}'''\n"


def outputs() -> dict[Path, str]:
    result = {}
    for src in sorted((ROOT / "judges").glob("*.md")):
        meta, body = parse(src)
        result[ROOT / "agents" / src.name] = claude_agent(meta, body)
        result[ROOT / "adapters/codex/agents" / f"{meta['name'].replace('-', '_')}.toml"] = codex_agent(meta, body)
    return result


def main(argv: list[str]) -> int:
    stale = []
    for path, text in outputs().items():
        if "--check" in argv:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    if stale:
        print("stale, run scripts/build_adapters.py:", *stale, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
