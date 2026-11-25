# feature-workflow

**A coding agent writes fast. You still re-check everything. This moves the bottleneck back to code.**

`feature-workflow` runs a feature or a bugfix through a fixed chain of phases. Every phase writes one short artifact, a **deterministic gate** (a script, not a model) checks it, judges from a *different model class* review the design and the code, and **you decide only at fixed points**: what we build, how, what "done" means, and the final review. You get a pass/fail report with numbers instead of re-verifying from scratch.

[Русская версия → README.ru.md](README.ru.md)

```mermaid
flowchart LR
  E[Enrich] --> R[Research] --> T{Triage}
  T -- full --> D[Design] --> A[Acceptance] --> P[Plan] --> C[Code]
  T -- short --> A2[Acceptance] --> C
  C --> Q[QA-check] --> DP[Deploy] --> V[Verify] --> RV[Review]
  classDef human fill:#fde68a,stroke:#b45309,color:#000
  class E,D,A,A2,RV human
```

Yellow = a human decision. Every arrow passes a gate: exit `0` go on, `1` the agent fixes it, `2` stop and ask you.

## Why

| Problem | What the workflow does |
|---|---|
| The agent "finishes" and you re-read everything | A gate script checks every artifact; the agent cannot move on until it passes |
| The agent quietly redesigns mid-code | Code that leaves the agreed file list or needs a bigger design exits `2` — you choose *fix in code* or *back to Design* |
| The author reviews its own work | Judges run on the **other** model class than the author (opus writes → sonnet judges, and back) |
| Acceptance criteria drift to fit the result | The approved criteria are snapshotted; changing a threshold fails the QA-check gate |
| Small tasks drown in ceremony | Triage picks a **short cycle** (no Design/Plan/QA-check) when the change is small and safe |

## Install

| Agent | Status | Install |
|---|---|---|
| **Claude Code** | works | `/plugin marketplace add SergeyKarpenko1/feature-workflow` then `/plugin install feature-workflow@feature-workflow` |
| **Codex CLI** | adapter built, **not yet tested end to end** | see below |
| Antigravity CLI, others | not built | gates and templates work anywhere; the skill runs in *inline mode* (no independent judge) |

**Codex CLI** (tested only as far as the installed `codex 0.139` CLI accepts these commands and the files parse):

```bash
codex plugin marketplace add SergeyKarpenko1/feature-workflow   # Codex reads the Claude-style marketplace.json
codex plugin add feature-workflow
git clone https://github.com/SergeyKarpenko1/feature-workflow /tmp/fw
python3 /tmp/fw/scripts/install_codex_agents.py                  # the two judges -> ./.codex/agents/
```

Codex plugins carry skills, not custom agents, hence the extra step. Codex judges inherit the parent's permissions, so they are read-only by instruction; for a hard guarantee run a judge with `codex exec -s read-only`.

Then in your project: `/feature my-feature` (Codex: mention the `feature` skill). On the first run the skill asks a few short questions (agent, tracker, whether to print a tracker card, base branch, check commands, the two models) and writes `.feature/config.toml` — only after you say yes.

Requirements: Python ≥ 3.11 (`tomllib`), `git`.

## The phases

| Phase | Who writes | Artifact | You |
|---|---|---|---|
| Enrich | agent interviews you | `01-enrich.md` | answer, confirm |
| Research | read-only subagent | `02-research.md` | — |
| Triage | gate | `cycle: short \| full` | may force `full` |
| Design | agent, then **design-judge** | `03-design.md` | **"design accepted"** |
| Acceptance | agent | `04-acceptance.md` | **"approved"** (snapshotted) |
| Plan | read-only subagent | `05-plan.md` (≤ 150 lines, no big code) | — |
| Code | agent, then **arch-judge** | the diff | only on escalation |
| QA-check | agent | `07-qa-check.md` | — |
| Deploy / Verify | agent | `09-report.md` | `manual` criteria |
| Review | you | — | read report + diff, commit |

The agent **never commits or pushes**. Edits are allowed only after you grant them for the current branch, recorded as `edits_allowed:` in the feature's `STATE.md`.

## Configuration

`.feature/config.toml` in your project ([full example](examples/config.example.toml)):

```toml
base_branch = "main"
features_dir = "docs/features"

[tracker]
kind = "jira"        # or "none"
task_card = true     # print title + description for the tracker after Enrich

[models]
strong = "opus"    # deciding phases; Codex: any model you have
fast = "sonnet"     # the rest; a judge always uses the other class

[checks]
commands = ["pytest -q", "ruff check ."]   # any shell commands; all must exit 0
known_failures = ""                        # tolerated pytest failures (baseline)

[triage]
max_short_files = 3
rules = [{ reason = "touches a contract", pattern = "^migrations/|schema" }]
```

## What it does *not* protect

Be clear about the limits:

- The scope gate compares the git diff with the research file list; it cannot see what a file *means*.
- Judges are models. They reduce, not remove, the chance of a wrong design getting through.
- The plugin cannot stop an agent from reading secrets by itself — configure your agent's permission rules for `.env`/credentials. The skill instructs against it; instructions are not enforcement.
- Your `checks.commands` run through the shell as written: they are your code, review them like any CI config.

## Repository layout

```
.claude-plugin/        plugin.json, marketplace.json
skills/feature/        SKILL.md (agent-neutral), scripts/feature_gate.py, templates/
judges/                the single source of the two judge prompts
agents/                generated for Claude Code        (scripts/build_adapters.py)
adapters/codex/agents/ generated for Codex CLI          (scripts/install_codex_agents.py copies them)
examples/              config.example.toml
tests/                 gate and adapter tests (pytest)
docs/                  design and implementation plan of the universal version
```

Edit judge prompts only in `judges/`, then run `python3 scripts/build_adapters.py`. Tests: `python3 -m pytest tests`.

## Roadmap

See [`docs/plan-v1.md`](docs/plan-v1.md): Antigravity adapter, a config-driven judge command (a judge from another *vendor*), a write-guard hook, ru/en artifact templates.

## License

MIT — see [LICENSE](LICENSE).
