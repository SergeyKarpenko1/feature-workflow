---
name: feature
description: Run a feature or bug through a phased agent workflow — enrich, research, triage, design, acceptance, plan, code, qa-check, deploy, verify, review — with a deterministic gate after every phase, judges on design and code, and the user deciding only at fixed points. Use on "/feature <name>", "/feature <folder>" (resume), "run this through the workflow", "new feature via workflow".
---

# /feature — phased workflow

This file is the operating checklist. Inside this workflow you write the phase
artifacts and, in Code, the code itself. That is an exception to any "do not edit
files" rule of the project, and it exists only after the user grants it for the
current branch (see Start) and records it as `edits_allowed:` in `STATE.md`.
Without that line you write nothing outside chat.

## Paths

- Project config `.feature/config.toml` — written once by Init, read at Start and after Enrich.
- Feature folder `F` = `<features_dir>/<YYYY-MM-DD>-<name>/` (`features_dir` from the config).
- Gate `G` = `python3 ${CLAUDE_SKILL_DIR}/scripts/feature_gate.py <phase> F`, run from the project root
  — exit `0` passed, `1` failed (you fix it), `2` escalation (stop, the user decides).
- Templates: `${CLAUDE_SKILL_DIR}/templates/`

## Init (first run)

Runs when `.feature/config.toml` does not exist, before anything else in Start.
Detect what you can (`git branch -r`, `package.json`, `pyproject.toml`, `Makefile`),
then ask in one message:
1. «Which agent do you use: Claude Code, Codex CLI, Antigravity, other?»
   This skill uses Claude Code tools (`Agent` subagents, `/model`). Any other
   answer → stop and say the skill targets Claude Code only for now.
2. «Which task tracker: Jira, Linear, GitHub Issues, other, none?»
3. Only if there is a tracker: «Write a task title and description for the tracker
   before every feature, besides the branch name?»
4. «Which commands must pass after code changes (tests, lint, types)?» and «the base
   branch for diffs» (propose the detected one).

Show the file below, write it only on an explicit yes, then continue with Start.
Full reference: `examples/config.example.toml` in the plugin repository.

```toml
language = "en"
agent = "claude"
base_branch = "main"
features_dir = "docs/features"
[tracker]
kind = "none"          # free name, or "none"
task_card = false      # false when kind = "none"
[checks]
commands = ["pytest -q"]
```

## Start or resume

- `/feature <name>`:
  0. No `.feature/config.toml` → Init first.
  1. Check the branch (`git branch --show-current`). On the base branch or an unrelated
     branch, give the user `git switch -c feature/<name> <base>` to run (never run it
     yourself) and wait. A clean tree is best; files already dirty are recorded by
     `G code-start` and excluded from the scope check.
  2. Ask the user, in one message: «may the agent edit files on branch `<branch>` for
     this feature?» and «feature or bug?». Only on an explicit yes create `F`, copy
     `templates/STATE.md`, set `edits_allowed: <branch>` and `kind:`.
  3. Then Enrich.
- `/feature <F>`: read `STATE.md`, continue at `phase:`. Read only the artifacts of
  earlier phases — not the conversation that produced them.

Copy a phase's template into `F` **when the phase starts**, never all at once
(an untouched `07-qa-check.md` would satisfy its own gate).

## Gate loop (every phase)

After writing a phase artifact run `G`. The gate itself appends the run to `## History`
and maintains `fails:` — never edit those by hand.
- `0` → set `phase:` to the next phase.
- `1` → fix the artifact, rerun. The third failure in a row comes back as `2`.
- `2` → stop. Show the `ESCALATE:` lines. For a scope or cycle escalation offer exactly
  two options: «fix in code» or «go back to Design»; for three failed runs show the last
  violations and ask. Never pick one yourself and never change the design from inside Code.

## Phases

| Phase | Who | Model | Artifact | Gate `<phase>` | User |
|---|---|---|---|---|---|
| Enrich | you + the user | session 1: opus | `01-enrich.md` | `enrich` | answers, confirms |
| Research | subagent (`Agent`, read-only) | `sonnet` | `02-research.md` | `research` | — |
| Triage | gate | — | `cycle:` in `STATE.md` | `triage` | — |
| Design | you, then `design-judge` | session 1: opus; judge `sonnet` | `03-design.md` | `design` | **“design accepted”** |
| Acceptance | you | session 1: opus | `04-acceptance.md` | `acceptance` | **“approved”** → run `G approve-acceptance` |
| Plan | subagent (`Agent`, read-only) | `sonnet` | `05-plan.md` | `plan` | — |
| Code | you, in session 2 | `code_model:` — opus for `core`, sonnet otherwise; `arch-judge` the other one | diff | `code`, then `arch-judge` | only on escalation |
| QA-check | you | session 3: sonnet | `07-qa-check.md` | `qa-check` | — |
| Deploy | you | session 3: sonnet | running service | health check | only if it fails |
| Verify | you | session 3: sonnet | `09-report.md` | `verify` | `manual` criteria |
| Review | user | — | — | — | reads report + diff, commits |

**Models.** Phases that decide (Enrich, Design, Acceptance, Code in `core`) run on
opus; phases a gate or a judge checks behind them run on sonnet. A judge is always the
other model class than the author of what it judges. You cannot switch the main
session's model — the user does, with `/model`, when opening a session: session 1 =
Enrich → Plan (opus), session 2 = Code (`code_model:`), session 3 = QA-check → Verify
(sonnet). At each session boundary tell the user which model to pick. If your own
model differs from what the phase needs, say so and ask before continuing. This split
is a hypothesis: if a sonnet phase starts producing more gate fails, escalations or
review findings, it goes back to opus.

**Short cycle** (`cycle: short`): Enrich → Research → Triage → Acceptance → Code →
Verify → Review. No Design, Plan, QA-check; Deploy only if Verify needs a running service.
In Code there is one pass over all of `## Affected files`, and `arch-judge` gets
`cycle: short` (it judges against `02-research.md`).

### Enrich
Interview the user about the task, but stop at the five `01-enrich.md` sections. Ask
about what only the user knows; look up the rest in the code. Write the answers into
`01-enrich.md`, not the transcript. «Open questions» ends as «none» or with every
question answered.

After `G enrich` passes, if `task_card = true` in the config: print in the chat, in the
config `language`, a task card built from `01-enrich.md` only (no invented numbers):
a title (one line, infinitive verb, ≤ 80 characters) and a description — «Problem»,
«What we do», «Rollback» (if a switch exists), «Acceptance criteria» (3–5 checkable
items). The branch name was already given at Start. Never write to the tracker; the
user pastes the card.

### Research
Dispatch one read-only subagent (`model: sonnet`) with: `01-enrich.md`, the project's
rules/docs map (`CLAUDE.md` or `AGENTS.md`), and the template `02-research.md`. It
returns the artifact text; you write it. «Affected files» lists the tests, stubs and
fixtures of every touched module too: a file outside the list escalates in Code. Put
backticks only around real paths from the repo root. For a bug, «Cause» comes with a trace/log id
and one `### Option N` per fix option.

### Triage
Run `G triage`. Tell the user the cycle and the rules that fired. The user may
override `short` → `full`, never the reverse.

### Design
Write `03-design.md`, run `G design`, then dispatch agent `design-judge` with `F`.
Parse the last ```json block. `fail` → fix and rerun the judge (counts toward
`fails`). `pass` → show the user the design and the judge's non-blocker findings;
wait for «design accepted» or remarks.

### Acceptance
Criteria table. Each criterion's method is `auto` or `manual`. «Baseline» is
«yes» when the old behaviour must be measured at the start of Code. After
«approved»: `G approve-acceptance`.

### Plan
Dispatch one read-only subagent (`model: sonnet`) with `02-research.md`,
`03-design.md` and the template `05-plan.md`; it returns the plan text, you write it
and run `G plan`. Phases only, no implementation: `### Phase N — <name>`, `Files:`,
`Done when:`, `Depends on:`. ≤ 150 lines, no code block over 5 lines.

After `G plan` passes (or after Acceptance in the short cycle): set `code_model:` in
`STATE.md` — `opus` when «Domain type» is `core`, `sonnet` otherwise — and tell the
user: open a new session, `/model <code_model>`, then `/feature F`.

### Code
0. Check `edits_allowed:` matches the current branch; otherwise stop and ask.
   Run `G code-start` once, **before any edit**: it records files already dirty
   (`preexisting.txt`). It refuses a second run — never delete its file yourself.
1. If «Baseline» is «yes»: deploy the old behaviour and take the baseline measurement
   (label `before`) — still before the first edit.
2. For each plan phase: edit → `G code` → fix until `0` (or stop on `2`).
3. Dispatch agent `arch-judge` with `F` and `cycle:`, and set the `Agent` call's
   `model` to the **other** class than `code_model:` (`opus` → `sonnet`,
   `sonnet` → `opus`). A `blocker` with `design_level: true` → stop, the two options
   above. Other blockers → fix, rerun `G code` and the judge.
4. Never `git commit` or `git push`. Then tell the user: open a new session,
   `/model sonnet`, then `/feature F` for QA-check → Verify.

### QA-check
Compare `04-acceptance.md` with the real code: response fields, names, flags. Fix
wording or add criteria; write what changed and why in `07-qa-check.md`. A threshold
of an approved criterion never changes — `G qa-check` fails on it; if a change is truly
needed, stop and ask.

### Deploy
Only when Verify needs a running service. Use the project's own run instructions
(README, Makefile, compose file) with the flags the design's «What changes» lists.
Never pass a secret on a command line. Check health; on failure stop and hand the user
the command that shows the service logs — they run it and paste back the relevant
lines without secrets.

### Verify
Measure every `auto` criterion (the `after` run) and compare with the baseline if one
was taken. For `manual` criteria put question → answer pairs under «For the user» —
never judge them yourself. Anything that needs credentials you must not read: write
the ready command for the user there. Fill «Results» with one row per criterion, then
`G verify`.

### Review
Give the user `09-report.md`, then the review depth by «Domain type»: `core` — whole
diff; `supporting` — report plus the judges' findings; `generic` — report and gates.
The user commits. After the merge, propose updates to the docs the change touched.

## Hard rules

- Never read `.env` / `.env.*`, key files or credential stores in any form, and never
  print environment variables. When a command needs a secret, write the command with an
  `export` line into the chat and let the user run it.
- Never edit the plugin's gates, judges or hooks, `.feature/config.toml`, the approved
  snapshot or `preexisting.txt` while the workflow runs: `G code` does not see those
  files, so changing them would rewrite the rules mid-game.
  `G approve-acceptance` runs once; a new snapshot needs the user to delete the old one.
- Never prefix a command with `cd` to the project root (you are already there) and
  search only inside explicit directories, never `.` or the repo root — security hooks
  block both, and every block costs a call.
- Judges and Research are subagents and never edit files. Code runs in the main session.
- No commits, no pushes, no MR from inside the workflow.
