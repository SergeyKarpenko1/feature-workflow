"""Copy the judge agents for Codex CLI into a project (or your home).

    python3 scripts/install_codex_agents.py             # ./.codex/agents  (this project)
    python3 scripts/install_codex_agents.py ~/.codex/agents   # every project

Codex plugins carry skills, not custom agents, so the two judges are installed separately.
"""

import shutil
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "adapters/codex/agents"


def main(argv: list[str]) -> int:
    target = Path(argv[0]).expanduser() if argv else Path.cwd() / ".codex/agents"
    target.mkdir(parents=True, exist_ok=True)
    for file in sorted(SRC.glob("*.toml")):
        shutil.copy2(file, target / file.name)
        print(f"installed {target / file.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
