# feature-workflow v1 — план реализации

> **Выполнение:** задачи идут по одной, код пишется в чате; в файлы — только по явной команде автора. Субагентов, правящих файлы, не запускать. Шаги отмечаются чекбоксами (`- [ ]`).

**Goal:** универсальный плагин `feature-workflow`: ядро (процесс, гейты, охранник, судьи, шаблоны, конфиг проекта) и адаптеры для Claude Code и Codex CLI.

**Architecture:** ядро в `core/` не знает ни вендора, ни проекта: всё проектное — в `.feature/config.toml` пользователя, всё вендорное — в `adapters/<agent>/`, которые собирает `scripts/build_adapters.py`. Скрипты — Python stdlib; судьи — промпты + внешняя или нативная команда.

**Tech Stack:** Python ≥ 3.11 (stdlib, `tomllib`), pytest через `uv run --with pytest`, bash для примеров, манифесты плагинов Claude Code / Codex, GitHub Actions.

**Spec:** `docs/design.md`

## Global Constraints

- Репозиторий: `~/projects/feature-workflow`, ветка `main`, лицензия MIT.
- Скрипты `core/scripts/*` — только stdlib, Python ≥ 3.11; зависимостей в рантайме нет.
- Ни одного слова, пути, имени или доменного примера исходного проекта. После каждой задачи: `python3 scripts/check_clean.py --denylist ~/.config/feature-workflow/denylist.txt` → пусто (Task 12; до неё — тот же поиск вручную). Список запрещённых слов в репозиторий не кладётся. Файл списка автор создаёт **до Task 1** (без него проверка «после каждой задачи» невыполнима); агент предлагает черновик в чате.
- Исходная локальная версия (у автора в его рабочем проекте: `.claude/skills/feature/`, `.claude/agents/*-judge.md`, спека процесса) — функциональная спецификация: читать можно, копировать строки нельзя.
- Frontmatter `SKILL.md`: только `name` и `description`.
- Коды выхода: гейт `0` прошло / `1` провал / `2` эскалация; `judge.py` `0` pass / `1` fail / `3` ошибка запуска; `guard.py` — по формату агента (§5.4 спеки).
- Языки артефактов: `ru` и `en`, одинаковая структура; язык — `language` в конфиге.
- Коммитов по задачам нет: один коммит в конце, по команде автора. Публикация на GitHub — не в этом плане.

## Review Focus

1. Конфиг без необязательных разделов (`[deploy]`, `[verify]`, `[judges]` пусты) — все гейты работают; критерии тогда только `manual`. Тест — Task 1.
2. Команда тестов не pytest (`npm test`, `go test`) — падения ищутся по `failure_regex` из конфига; нет итоговой строки или код выхода вне `ok_codes` → провал, не ложное «прошло». Тест — Task 3.
3. Хук получает незнакомый или битый JSON — охранник пропускает и пишет предупреждение в stderr, а не блокирует всё подряд. Тест — Task 5.
4. Порог критерия с опечаткой или метрика не пришла — критерий «не прошло» с понятным сообщением, без трейсбека. Тест — Task 4.
5. Артефакт с CRLF и BOM (сохранён в Windows) — гейты читают его без ложных нарушений. Тест — Task 2.

---

## Файлы

| Файл | Ответственность |
|---|---|
| `core/scripts/fw_config.py` | загрузка и проверка `.feature/config.toml` |
| `core/scripts/feature_gate.py` | гейты фаз, triage, code-start, approve, run-verify |
| `core/scripts/guard.py` | охранник секретов и защищённых файлов, формат ответа Claude/Codex |
| `core/scripts/judge.py` | запуск судьи по команде из конфига, разбор вердикта |
| `core/judges/{design,arch}.md`, `verdict.schema.json` | промпты судей и схема вердикта |
| `core/templates/{ru,en}/*` | шаблоны артефактов и `STATE.md` |
| `core/skills/feature/SKILL.md`, `core/skills/feature-init/SKILL.md` | процесс и настройка |
| `core/tests/*` | pytest на скрипты |
| `scripts/build_adapters.py`, `scripts/check_clean.py` | сборка адаптеров, проверка чистоты |
| `adapters/{claude,codex}/…`, `.claude-plugin/marketplace.json` | манифесты и обвязка |
| `examples/…`, `docs/{config,vendors,how-it-works}.md`, `README.md`, `LICENSE`, `.github/workflows/ci.yml` | примеры, документация, CI |

---

### Task 1: Каркас и конфиг проекта

**Files:** Create `core/scripts/fw_config.py`, `core/tests/test_config.py`, `examples/config.example.toml`, `LICENSE` (MIT, `SergeyKarpenko1`), `.gitignore`.

**Interfaces — Produces:**
- `@dataclass Config`: `language: str`, `base_branch: str`, `test: TestCommand | None`, `lint: str | None`, `triage: list[TriageRule]`, `max_short_files: int` (3), `layers: dict[str, list[str]]`, `domains: dict[str, list[str]]`, `knowledge: list[str]`, `secrets: SecretRules`, `deploy: Deploy | None`, `verify: dict[str, str]`, `models: dict[str, str]`, `judges: JudgeConfig`, `agent: str | None` (информационное: `claude`, `codex` или другое имя; пишет `/feature-init`), `tracker: Tracker`, `timeout_sec: int` (600, из `[commands] timeout_sec`; общий лимит для тестов, команд `[verify]` и health-проверки).
- `TestCommand(command: str, failure_regex: str, summary_regex: str, ok_codes: list[int], known_failures: str | None)` (`known_failures` — файл с уже известными падениями тестов; не путать со снимком «до» у Verify); по умолчанию — значения для pytest: `^(?:FAILED|ERROR) (?P<id>\S+)`, `\b\d+ (passed|failed)\b`, `[0, 1]`.
- `TriageRule(name: str, paths: list[str], reason: str)`; `SecretRules(read_globs: list[str], command_regexes: list[str], protected_writes: list[str])` — у `protected_writes` всегда есть `.feature/config.toml`, `**/*.approved.md`, `**/preexisting.txt`.
- `Deploy(start: str, health: str, stop: str)`; `JudgeConfig(mode: str = "native", design: str | None, arch: str | None)`; `Tracker(kind: str = "none", task_card: bool = False)` — `kind` свободное имя трекера задач (`jira`, `linear`, любое другое) или `none`; раздел `[tracker]` необязателен.
- `load_config(root: Path) -> Config` (ищет `root/.feature/config.toml`); `check_config(cfg: Config, root: Path) -> list[str]`; `ConfigError`.
- `glob_match(path: str, pattern: str) -> bool` — единственный матчер глобов в проекте (triage, layers, domains, guard); `fnmatch` не использовать: `**/` в нём требует хотя бы одного `/`, и файлы в корне не совпадают. Перевод в регулярку: `**/` → `(?:.*/)?`, `**` → `.*`, `*` → `[^/]*`, `?` → `[^/]`; путь в POSIX-виде.

- [ ] **Step 1: Tests** в `test_config.py`: `test_minimal_config_loads` (только `language`, `base_branch` → пустые `triage`/`verify`, `deploy is None`, `test` с pytest-умолчаниями при наличии `[commands] test`); `test_protected_writes_always_present`; `test_bad_regex_reported` (`failure_regex = "("` → нарушение с именем поля); `test_unknown_language_reported` (`"de"`); `test_verify_name_with_spaces_rejected`; `test_tracker_defaults` (без раздела `[tracker]` → `kind == "none"`, `task_card is False`); `test_task_card_requires_tracker` (`task_card = true` при `kind = "none"` → нарушение с именем поля); `test_example_config_is_valid` (`examples/config.example.toml`, `root=examples/`, пути в проверке — относительно `root` → `check_config == []`); `test_glob_match_root_level` (`glob_match("x.approved.md", "**/*.approved.md")` и `glob_match("preexisting.txt", "**/preexisting.txt")` истинны, `glob_match("a/b/c.py", "a/*.py")` ложно, `glob_match("a/b/c.py", "a/**")` истинно).
- [ ] **Step 2: RED.** `uv run --with pytest pytest core/tests/test_config.py -q` → `ModuleNotFoundError`.
- [ ] **Step 3: Implement** `fw_config.py` (`tomllib`, dataclasses, `re.compile` для проверки регулярок, `glob_match`) и пример конфига для вымышленного проекта (`app/`, `migrations/`, `api/schemas/`).
- [ ] **Step 4: GREEN.** Та же команда → PASS.

### Task 2: Шаблоны и гейты структуры

**Files:** Create `core/templates/{ru,en}/{STATE.md,01-enrich.md,02-research.md,03-design.md,04-acceptance.md,05-plan.md,07-qa-check.md,09-report.md}`, `core/scripts/feature_gate.py`, `core/tests/test_gate_structure.py`.

**Interfaces:**
- Consumes: `load_config`, `Config.language`, `Config.verify` (Task 1).
- Produces: `HEADINGS: dict[str, dict[str, list[str]]]` (язык → артефакт → разделы); `section(text, heading) -> str | None`; `artifact_paths(body) -> list[str]`; `check_<phase>(folder: Path, cfg: Config) -> list[str]` для `enrich`, `research`, `design`, `acceptance`, `plan` (`verify` — только в Task 4); `run_gate(phase: str, folder: Path, problems: list[str]) -> int` — общая обвязка всех гейтов: при провале увеличивает в `folder/STATE.md` строку `failures: <phase>=<n>`, при успехе сбрасывает её; код выхода `0` прошло, `1` провал, `2` эскалация при `n ≥ 3`; CLI `feature_gate.py <phase> <folder> [--root DIR]` и `feature_gate.py check-config [--root DIR]` (печатает `check_config`, код 1 при нарушениях).

Поведение переносится с локальной версии (разделы, пустое тело = нет раздела, HTML-комментарий = пусто, пути с пробелами и суффиксами `:N`, `#LN`, mermaid в дизайне, план ≤ 150 строк, блоки кода ≤ 5 строк, файлы плана ⊆ файлы research). Новое:
- критерий тест-плана: `| id | what/что | check/способ | threshold/порог | repeats/повторы |`; способ — `verify:<имя>` (имя есть в `cfg.verify`) или `manual`; порог — `pass` или `<metric> <op> <число>`, `op ∈ {>=, <=, >, <, ==}`;
- `questions.tsv` в ядре не проверяется;
- в `04-acceptance` есть раздел `## Baseline` со значением `да` или `нет`; при `да` гейт `verify` (Task 4) требует снимок «до» `runs/before.json`.

- [ ] **Step 1: Tests:** перенести по смыслу 12 структурных тестов локальной версии на оба языка (параметризация `language`), плюс `test_unknown_verify_name_reported`, `test_threshold_syntax_checked` (`hit rate >= x` → нарушение), `test_crlf_bom_artifact_ok` (Review Focus 5), `test_blank_templates_fail_every_gate[ru|en]`, `test_ru_en_same_structure` (у `HEADINGS["ru"]` и `HEADINGS["en"]` одинаковые ключи и число разделов; в `templates/ru` и `templates/en` одинаковые имена файлов), `test_third_failure_escalates` (три провала подряд → код `2`), `test_failure_counter_resets_on_success` (провал, успех, провал → `1`), `test_baseline_section_required` (нет `## Baseline` → нарушение).
- [ ] **Step 2: RED.** `uv run --with pytest pytest core/tests/test_gate_structure.py -q`.
- [ ] **Step 3: Implement** шаблоны (подсказки в `<!-- -->`) и структурную часть `feature_gate.py`.
- [ ] **Step 4: GREEN.**

### Task 3: Triage, code-start и гейт Code

**Files:** Modify `core/scripts/feature_gate.py`; Create `core/tests/test_gate_code.py`.

**Interfaces — Produces:** `triage_reasons(files, new_files, research_text, cfg) -> list[str]`; `changed_files(base, repo) -> tuple[list[str], set[str]]` (`git … -z`); `code_start(folder, repo, cfg) -> list[str]` (отказ при повторном снимке); `scope_violations(files, allowed, preexisting) -> list[str]`; `test_problems(returncode, output, known_failures_text, cfg.test) -> list[str]`; `check_code(folder, repo, cfg) -> tuple[list[str], int]` (нарушения и код выхода гейта через `run_gate`); CLI-подкоманды `triage`, `code-start`, `code`.

Правила triage — только из `cfg.triage` (glob через `glob_match` из Task 1 по POSIX-пути), плюс встроенные: больше `cfg.max_short_files` файлов, ≥ 2 слоя из `cfg.layers`, новый файл под правилом с `name = "new-port"`, больше одного варианта в разделе причины, непустые «затронутые инварианты». Lint — `cfg.lint` с `{files}`; тесты — `cfg.test`. Нет `cfg.test` → шаг пропускается с предупреждением в выводе (не провал).

- [ ] **Step 1: Tests:** перенести 5 тестов triage/scope/changed_files локальной версии под конфиг; `test_npm_style_failures_parsed` (`failure_regex` для `✕ (?P<id>.+)`; новая строка → провал); `test_crash_code_outside_ok_codes_fails`; `test_missing_summary_fails` (Review Focus 2); `test_code_start_refuses_second_run`; `test_no_test_command_is_warning_not_failure`; `test_test_command_timeout_fails` (команда дольше `cfg.timeout_sec` → провал с сообщением «таймаут»).
- [ ] **Step 2: RED.** `uv run --with pytest pytest core/tests/test_gate_code.py -q`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: GREEN.**

### Task 4: Утверждение тест-плана, QA-check, Verify

**Files:** Modify `core/scripts/feature_gate.py`; Create `core/tests/test_gate_verify.py`.

**Interfaces — Produces:** `approve_acceptance(folder) -> list[str]` (отказ при повторе); `check_qa_check(folder, cfg) -> list[str]` — сравнивает **способ, порог и повторы** (`cells[2:5]`); `run_verify(folder, cfg, label, root) -> list[str]` — для каждого критерия `verify:<имя>` запускает `cfg.verify[имя]` `повторы` раз, берёт код выхода и последнюю строку stdout как JSON метрик (если она JSON), считает «прошло» по порогу и пишет `folder/runs/<label>.json` (`{id: {"runs": [...], "passed": bool, "message": str}}`); `check_verify(folder, cfg) -> list[str]` — в `09-report.md` строка на каждый критерий, и у `verify:`-критериев колонка «прошло» совпадает с `runs/after.json`; при `## Baseline: да` требует и `runs/before.json` с результатом по каждому `verify:`-критерию (единственное определение `check_verify`); `deploy_up(cfg, root) -> list[str]` — запускает `cfg.deploy.start`, опрашивает `cfg.deploy.health` до `cfg.timeout_sec`; `deploy_down(cfg, root) -> list[str]` — запускает `cfg.deploy.stop`; при `cfg.deploy is None` оба возвращают `[]` и печатают «deploy пропущен». CLI: `approve-acceptance`, `qa-check`, `run-verify <folder> <label>`, `verify`, `deploy-up`, `deploy-down`.

Порог разбирается без `eval`: `pass` или регулярка `^(\w+)\s*(>=|<=|>|<|==)\s*(-?\d+(\.\d+)?)$`; «прошло» для `repeats > 1` — все повторы прошли. Каждый запуск ограничен `cfg.timeout_sec`; превышение → критерий «не прошло» с сообщением «таймаут».

- [ ] **Step 1: Tests:** перенести 4 теста qa-check + `test_qa_check_flags_method_change`; `test_run_verify_pass_and_metric` (подставные команды `python3 -c "print('{\"hit_rate\": 0.95}')"` и `exit 1`); `test_missing_metric_fails_with_message` и `test_bad_threshold_fails_with_message` (Review Focus 4); `test_report_claiming_pass_against_runs_fails`; `test_approve_refuses_second_snapshot`; `test_verify_timeout_fails` (`sleep` дольше лимита); `test_baseline_requires_before_json` (`## Baseline: да` без `runs/before.json` → нарушение); `test_deploy_skipped_when_empty` (`cfg.deploy is None` → `[]`); `test_deploy_up_waits_for_health` (health отвечает со второй попытки → успех; не отвечает до лимита → нарушение).
- [ ] **Step 2: RED.** `uv run --with pytest pytest core/tests/test_gate_verify.py -q`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: GREEN.**

### Task 5: Охранник

**Files:** Create `core/scripts/guard.py`, `core/tests/test_guard.py`.

**Interfaces — Produces:** `decide(payload: dict, rules: SecretRules) -> str | None` (причина запрета или `None`); `extract(payload: dict) -> tuple[str, str | None, str | None]` (имя инструмента, команда, путь) для формата Claude/Codex (`tool_name`, `tool_input.command|file_path`); CLI `guard.py --format claude|codex [--root DIR]`, читает stdin. Корень проекта — `payload["cwd"]`, `--root` его перекрывает. Нет или битый `.feature/config.toml` → применяются умолчания и пишется предупреждение в stderr (охранник не падает и не блокирует всё подряд).

Умолчания правил (дополняются конфигом): чтение `.env`, `.env.*`, `*.pem`, `id_rsa*`; команды-читатели рядом с этими путями; `printenv`/`env` целиком; `/proc/*/environ`; `docker … inspect|logs`, `docker-compose … logs`; `docker exec … env|printenv`; рекурсивный `grep|rg` по `.`; запись в `protected_writes` — **только инструментами записи с `file_path`** (Write/Edit и аналоги, путь сравнивается через `glob_match`). Запись через Bash (`>`, `>>`, `tee`, `sed -i`) не перехватывается: это сознательная граница, она проговаривается в README. Ответ: exit 2, причина в stderr. Битый JSON — exit 0, предупреждение в stderr.

- [ ] **Step 1: Tests:** таблица случаев из самопроверки локальной версии (23 строки, переписанных на вымышленные имена) × два формата; `test_protected_config_write_denied`; `test_protected_write_at_repo_root_denied` (`preexisting.txt`, `x.approved.md` в корне); `test_bash_redirect_to_protected_not_blocked` (фиксирует границу: команда `echo > .feature/config.toml` проходит); `test_missing_config_uses_defaults_with_warning`; `test_root_taken_from_payload_cwd`; `test_malformed_payload_allows_with_warning` (Review Focus 3).
- [ ] **Step 2: RED.** `uv run --with pytest pytest core/tests/test_guard.py -q`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: GREEN.**

### Task 6: Судьи

**Files:** Create `core/judges/design.md`, `core/judges/arch.md`, `core/judges/verdict.schema.json`, `core/scripts/judge.py`, `core/tests/test_judge.py`, `core/tests/fake_cli.py`; Modify `examples/config.example.toml` (три шаблона команд судьи).

**Interfaces:**
- Consumes: `Config.judges`, `Config.knowledge`.
- Produces: `build_prompt(kind: str, folder: Path, cfg: Config, diff: Path | None) -> str`; `extract_verdict(stdout: str, out_file: Path | None) -> dict` (ищет `structured_output` в JSON-конверте, иначе JSON из `out_file`, иначе последний ```json-блок); `validate_verdict(v: dict) -> list[str]`; CLI `judge.py design|arch <folder> [--diff FILE] [--cycle full|short]`.

Шаблон команды в конфиге — строка с `{prompt_file}`, `{schema_file}`, `{out_file}`; `judge.py` подставляет значения через `shlex.quote` и запускает команду с `shell=True` (шаблон содержит перенаправление `<`; пути могут содержать пробелы); в `examples/config.example.toml` два готовых шаблона из спеки §3 (`claude -p --bare …`, `codex exec -s read-only --output-schema {schema_file} -o {out_file} - < {prompt_file}`). Промпты судей — общие проверки спеки §5.3; поиск по репо только явными путями из `cfg.knowledge` и исходных каталогов, никогда по `.`.

- [ ] **Step 1: Tests** с `fake_cli.py` (печатает заданный конверт): `test_claude_style_envelope`, `test_codex_out_file`, `test_fenced_json_fallback`, `test_invalid_verdict_is_error_code_3`, `test_fail_iff_blocker`, `test_prompt_has_no_root_search` (в собранном промпте нет `grep -r … .`), `test_paths_with_spaces` (`tmp_path` с пробелом в имени, `fake_cli.py` читает файл по этому пути).
- [ ] **Step 2: RED.** `uv run --with pytest pytest core/tests/test_judge.py -q`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: GREEN.**

### Task 7: Скиллы

**Files:** Create `core/skills/feature/SKILL.md`, `core/skills/feature-init/SKILL.md`, `core/tests/test_skills.py`.

`feature/SKILL.md` — процесс по спеке §5.1 и локальной версии, на английском, с плейсхолдером `{{FW_ROOT}}` для путей к скриптам и шаблонам (подставляет Task 8). Встроенные разделы «Interview (Enrich)» и «Signature dump (Research)». Первый запуск: если нет `.feature/config.toml`, скилл сначала запускает `feature-init`, и только потом Enrich. Карточка задачи: при `tracker.task_card = true` после прохождения гейта Enrich скилл выдаёт в чат (на языке `language`) название и описание задачи для трекера (проблема, что делаем, откат, критерии приёмки), собранные из `01-enrich.md`; имя ветки выдаётся на старте, как и раньше. В трекер агент ничего не пишет. Модели — из `cfg.models` (`decide`/`check`), судьи — `judge.py` или нативный сабагент по `cfg.judges.mode`. `feature-init/SKILL.md` — шаги спеки §7, выдаёт блок правил запрета секретов для агента пользователя. Спрашивает: (1) агента, если не определился по окружению (Claude Code, Codex CLI или другой; для «другого» говорит, что хука охранника и готовых скиллов нет); (2) трекер задач (Jira, Linear, GitHub Issues, другой или нет); (3) только если трекер есть — нужна ли карточка задачи перед каждой фичей. Ответы пишет в `agent` и `[tracker]` конфига.

- [ ] **Step 1: Tests:** `test_frontmatter_portable` (ключи ⊆ `{name, description}`); `test_every_script_reference_exists` (каждый `{{FW_ROOT}}/…` указывает на файл в `core/`); `test_feature_skill_runs_init_when_no_config` (в теле `feature/SKILL.md` описан первый запуск: нет `.feature/config.toml` → `feature-init`); `test_init_asks_agent_and_tracker` (в `feature-init/SKILL.md` есть вопросы про агента, трекер и карточку задачи); `test_no_vendor_only_tool_names` (в теле нет имён инструментов в обратных кавычках — регулярка `` `(Agent|Skill|TodoWrite)` `` — только описания действий; слово «Agent» в обычном тексте допустимо).
- [ ] **Step 2: RED → Step 3: Implement → Step 4: GREEN.** `uv run --with pytest pytest core/tests/test_skills.py -q`.

### Task 8: Сборка и адаптер Claude Code

**Files:** Create `scripts/build_adapters.py`, `adapters/claude/.claude-plugin/plugin.json`, `adapters/claude/agents/{design-judge,arch-judge}.md`, `adapters/claude/hooks/hooks.json`, `.claude-plugin/marketplace.json`, `core/tests/test_build.py`.

**Interfaces — Produces:** `build(agent: str, out: Path) -> None` (копирует из `core/` только `skills/`, `scripts/`, `judges/`, `templates/` в `adapters/<agent>/`, заменяет `{{FW_ROOT}}` значением агента; `core/tests/` и `__pycache__` не копируются; файлы, написанные руками — `plugin.json`, `hooks.json`, `agents/` — не трогаются); `check(agent) -> list[str]` (сгенерированные каталоги == ядро); CLI `build_adapters.py build|check [agent]`.

Claude: `{{FW_ROOT}}` → `${CLAUDE_PLUGIN_ROOT}`; судьи-агенты без `model:` (модель — параметром вызова); хук `PreToolUse` → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guard.py" --format claude`; `marketplace.json` → `{"source": "./adapters/claude"}`.

- [ ] **Step 1: Tests:** `test_build_is_idempotent`, `test_check_detects_drift`, `test_claude_manifest_fields` (`name == "feature-workflow"`, `license == "MIT"`).
- [ ] **Step 2–4:** RED → Implement → GREEN.
- [ ] **Step 5: Validate.** `claude plugin validate adapters/claude --strict` → без ошибок.

### Task 9: Адаптер Codex CLI

**Files:** Create `adapters/codex/…` (манифест по спецификации Codex), `adapters/codex/hooks/hooks.json`.

- [ ] **Step 1: Read the spec.** Официальная страница плагинов Codex (developers.openai.com/codex/plugins и руководство разработчика плагинов): структура манифеста, где лежат скиллы и хуки, переменная корня плагина. Записать находки в `docs/vendors.md`. Если переменной корня нет — `Ruling:` в журнале (например, путь относительно скилла) и та же подстановка в `build_adapters.py`.
- [ ] **Step 2: Build.** `{{FW_ROOT}}` для Codex; хук `PreToolUse` → `guard.py --format codex`; судьи по умолчанию `mode = "command"` с `codex exec -s read-only`.
- [ ] **Step 3: Test** `test_codex_build_check` в `core/tests/test_build.py` → GREEN.
- [ ] **Step 4: Local install.** Автор: `codex plugin marketplace add ~/projects/feature-workflow`, `/plugins` → установлен, скилл виден в `/skills`.

### Task 10: Примеры

**Files:** Create `examples/sample-project/` (маленькое приложение на Python: `app/`, `tests/`, `migrations/`, `.feature/config.toml`, одна команда `[verify]` с метрикой), `examples/verify/chat_api_eval.sh` (вымышленный чат-API, вопросы из `questions.tsv`, печатает `{"answered": N, "total": M}`).

- [ ] **Step 1:** `feature_gate.py check-config` на `examples/sample-project` → `[]`; тесты проекта проходят; `run-verify` на подставном критерии печатает метрику.

### Task 11: Документация

**Files:** Create `README.md` (русский, затем английский, разделы спеки §9), `docs/config.md` (все поля Task 1 с примерами), `docs/vendors.md` (таблица спеки §3 со ссылками и датами), `docs/how-it-works.md` (схема фаз mermaid, кто где решает, модели и судьи).

- [ ] **Step 1:** каждая команда установки и запуска в README выполнена хотя бы раз в Task 8–9, 13 (или помечена «не проверено»); разделы README на двух языках совпадают по составу. Шаблоны команд судьи для Claude Code, до которых не дошёл Task 13, помечаются в `docs/vendors.md` «не проверено».
- [ ] **Step 2:** раздел README «Безопасность» (ru и en) прямо говорит: охранник защищает `.feature/config.toml`, `*.approved.md`, `preexisting.txt` от записи только инструментами записи; команды Bash (`echo >`, `sed -i`, `tee`) не перехватываются; хук — страховка, а не граница безопасности.

### Task 12: Проверка чистоты и CI

**Files:** Create `scripts/check_clean.py`, `.github/workflows/ci.yml`, `core/tests/test_check_clean.py`.

**Interfaces — Produces:** `scan(root: Path, words: list[str]) -> list[str]` (`файл:строка: слово`, регистр игнорируется, `.git/` пропускается); CLI `check_clean.py --denylist FILE [--root DIR]`, код 1 при находках.

- [ ] **Step 1–4:** RED → Implement → GREEN (`test_scan_finds_word_case_insensitive`, `test_git_dir_skipped`).
- [ ] **Step 5:** CI: pytest, `build_adapters.py check`, проверка JSON-манифестов (`claude plugin validate` в CI не запускается — CLI в раннере нет, только локально перед публикацией); `check_clean` в CI не запускается (списка там нет) — только локально, перед каждым коммитом и публикацией.
- [ ] **Step 6:** `check_clean.py --denylist ~/.config/feature-workflow/denylist.txt` по всему репо → пусто. Список составляет автор; агент предлагает черновик в чате, в файл не пишет.

### Task 13: Сквозная проверка (Claude Code и Codex)

- [ ] **Step 1:** Сценарий в `docs/e2e.md`: на `examples/sample-project` — `/feature-init` → `/feature add-health-metric` (короткий цикл) → отчёт; ожидаемые ответы и остановки по шагам.
- [ ] **Step 2: Claude Code.** Автор ставит плагин из локальной папки и проходит сценарий. Каждое расхождение — запись в журнале и исправление (TDD, если это код).
- [ ] **Step 3: Codex CLI.** То же. Плюс судья: `codex exec -s read-only --output-schema core/judges/verdict.schema.json -o v.json - < prompt` на подложенном дефекте → `fail`.
- [ ] **Step 4:** Обе прошли → v1 готов к коммиту и публикации (по команде автора).
