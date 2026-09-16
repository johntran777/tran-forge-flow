# Tran Forge — project configuration

<!-- Copy this file to your repo root as `tran-forge.config.md` and adjust. This file is the per-project
     source of truth: when it disagrees with the article it points at, this file wins. To target a different
     stack, point `article:` at your own article file and swap the commands below. -->

## Project

- language: java
- build_tool: maven
- article: .claude/skills/tran-forge/constitution/article-java-maven.md
- base_branch: main
- requirements_file: requirements.txt   # created on demand — see below

## Layout

- production_src: src/main/java
- unit_test_src: src/test/java
- features_dir: src/test/resources/features
- acceptance_test_src: src/test/java/**/acceptance

## Commands

- build: mvn -q -DskipTests compile
- unit_tests: mvn -q test -Dtest='*Test,!RunCucumberTest'
- acceptance_tests: mvn -q test -Dtest=RunCucumberTest
- all_tests: mvn -q test
- coverage: mvn -q verify   # report: target/site/jacoco/ (jacoco.xml for machine reading)
- mutation_full: mvn -q test-compile org.pitest:pitest-maven:mutationCoverage
- mutation_targeted: mvn -q test-compile org.pitest:pitest-maven:mutationCoverage -DtargetClasses={classes} -DtargetTests={tests}
- mutation_report: target/pit-reports

## Thresholds

<!-- Both gates apply to the classes the cycle TOUCHED, not the whole project — on a brownfield repo the
     full-project mutation score reflects legacy code no role is allowed to fix, so gating on it would fail
     every cycle. The Mutator still runs and reports the full-project score, as information only. -->

- mutation_score_min: 85
- line_coverage_min: 90

## Token budgets

<!-- Context discipline (see the skill's "Prime directive — token discipline").

     THIS WHOLE BLOCK IS OPTIONAL. Every key has a built-in default, shown below, so a config written before
     the block existed stays valid — preflight resolves the missing keys and says which it defaulted. Set a
     key only to override it.

     context_budget_tokens (default 100000) — the per-context ceiling the flow is designed around: the lead,
     every role, and every report are shaped to finish inside it. It is a design ceiling, not a runtime
     meter — no agent can query its own context size, so it is governed structurally (one cycle per context,
     fresh spawn per role, paths not contents) rather than measured. Raise it only if you have reason to
     trust your model's judgement further out; lowering it makes the flow recommend fresh contexts sooner.

     report_max_lines (default 60) — caps the PROSE of a role's completion report; an oversized report goes
     back to its author to compress. The carve-out: findings/verdict TABLES are never truncated — the
     dedupe, the cycle report and /tran-forge-history all consume those rows, and a cut row is
     unrecoverable. Compress rationale, not rows.

     ledger_dir (default .tran-forge) — where the lead keeps the per-cycle ledger (started right after
     Gate 1, appended per phase, finalized and committed at cycle close, Phase 8):
     the committed, durable record of verdicts, findings, contradiction calls, incidents and gate decisions.
     It is what makes "next feature in a fresh session" lossless and gives /tran-forge-history an on-disk
     source for the sections that otherwise only exist in scrollback. -->

- context_budget_tokens: 100000
- report_max_lines: 60
- ledger_dir: .tran-forge

## Intake

<!-- Optional Jira intake: `/tran-forge PROJ-1234` pulls the ticket through the Atlassian MCP and distils it
     into a plain-text entry in `requirements_file` before the Phase 0 grilling.

     The file named by `requirements_file` does NOT need to exist up front. If it is missing or empty and you
     invoke `/tran-forge` with no argument, preflight asks you for a Jira ticket or a plain-text requirement,
     then creates the file and seeds it with your answer. The flow never invents a feature to get started. -->

- jira_enabled: true
- jira_project_key:            # e.g. PROJ — lets a bare `/tran-forge 1234` resolve; blank = full keys only
- jira_write_back: false       # true only lets the lead OFFER to comment/transition at cycle close; still needs per-cycle confirmation

## Artifacts

<!-- Defaults for the cycle-close retention question. The lead always asks; these are the pre-selected answers.
     "keep" is almost always right: the .feature files ARE the executable specification. -->

- keep_requirements: true      # keep the refined requirement entry committed in requirements_file
- keep_features: true          # keep the .feature files committed in features_dir

## Review (Codex — Phases 3–5, right after the Coder)

<!-- Three external reviews driven through the Codex CLI, so a different model family grades the work:
     design & architecture (Phase 3), then security/OWASP (Phase 4), then performance (Phase 5).
     Findings route back to the Coder, which applies them one at a time in review-fix mode.
     One switch and one model govern all three; a skipped review is reported as skipped, never as passed.
     Verify the slug is still current before pinning a new one:
       python3 -c "import json;[print(m['slug'],m.get('priority')) for m in json.load(open('$HOME/.codex/models_cache.json'))['models']]"
     `codex_sandbox` must stay read-only — these reviewers must not be able to modify the repo. -->

- codex_enabled: true
- codex_model: gpt-5.6-sol
- codex_reasoning_effort: xhigh
- codex_sandbox: read-only
- performance_budget:          # optional, project-specific: what counts as a Blocker, e.g. "no N+1; every collection endpoint paginated"

## Manual test (Phase 7 — the second human gate)

<!-- Phase 7 dispatches by SURFACE: every surface the cycle's diff touched gets the one mode that can
     actually see it. Web → Playwright. Native → Maestro (or another `mobile_driver`). Network edge → curl.
     Neither → the REPL. A surface with no capable mode is reported BLOCKED, never PASS.

     manual_test_mode — modes STACK; a change spanning a web UI and its API is tested browser+service, and a
     change to code shared by a web shell and a native app is tested browser+mobile:
       auto    — browser if the diff touched ui_src_paths, mobile if it touched mobile_src_paths,
                 service if it touched a REST/network edge, else library (default)
       browser — drive the rendered WEB UI through Playwright MCP at `ui_base_url`
       mobile  — build the native app and drive it on a simulator/emulator via `mobile_driver` (see below)
       service — boot via `run_app` and drive it over HTTP at `app_base_url`
       library — drive the public API via `library_repl` / the repo's CLI (correct for katas and domain libs)
       skip    — no manual phase; recorded as skipped in the cycle report -->

- manual_test_mode: auto
- run_app: mvn spring-boot:run
- app_base_url: http://localhost:8080
- app_health_path: /actuator/health
- library_repl: jshell --class-path target/classes   # library mode's REPL; e.g. `npx tsx` or `node` on a TS repo

<!-- ui_src_paths drives BOTH the auto-mode choice and the WEB arm of the surface guard: when the diff touches
     one of these paths and no browser-capable mode is available, the manual tester must report those items
     ⚠ BLOCKED — never ✅ PASS. Leave it BLANK only for projects with genuinely no web UI (a blank value means
     the web arm of the guard can never fire). Comma-separated globs, e.g.:
       src/main/resources/templates/**, src/main/resources/static/**, src/main/frontend/**, **/*.tsx, **/*.vue
     Requires Playwright MCP: {"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}} in .mcp.json.

     Scope note: browser mode covers WEB UIs only, including responsive layouts via device emulation. Device
     emulation is a resized browser with a spoofed user-agent — it is never evidence about a native build.
     Native apps are the `mobile` mode's job, and the two arms of the guard are independent: passing the web
     shell says nothing about the native app, even when both consume the same shared code. -->

- ui_src_paths:
- ui_base_url: http://localhost:8080
- ui_start:                    # optional: command to start the UI when it boots separately from the API

<!-- mobile_src_paths drives the auto-mode choice and the NATIVE arm of the surface guard, exactly as
     ui_src_paths does for web. Keep the two keys separate: in a repo where one library feeds both a web shell
     and a native app, that shared path belongs in BOTH lists, so a change to it is tested browser+mobile.
     Blank means the native arm of the guard can never fire — correct for a repo with no native app, dangerous
     for one that has it. Comma-separated globs, e.g.:
       apps/mobile-app/**, libs/**

     mobile_driver — how the native app is driven:
       maestro — `maestro test` against a booted simulator/emulator. The default recommendation: a plain CLI
                 (no MCP dependency), implicit waits (so far fewer FLAKY rows than Appium), and
                 `--debug-output` yields both a view-hierarchy dump to assert on and screenshots for the human.
       detox   — `detox test` (grey-box, RN-only; syncs with the RN bridge; needs a detox build config)
       appium  — `npx wdio run <mobile_wdio_config>` (black-box W3C; slowest and flakiest of the three)
       none    — no mobile driver available; `mobile` mode cannot run, and any diff touching
                 mobile_src_paths is reported ⚠ BLOCKED rather than approximated -->

- mobile_driver: none
- mobile_platform: ios         # ios | android | ios+android — platforms stack, like modes
- mobile_src_paths:
- mobile_prepare:              # optional: deps in a fresh worktree, e.g. `yarn install --immutable`
- mobile_build:                # command producing the installable binary, e.g. `yarn mobile-app:build:e2e:ios`
- mobile_app_binary:           # path to the built .app/.apk — asserted to exist and be fresh before any test
- mobile_device: simulator     # simulator | emulator | real — `real` needs explicit per-cycle user opt-in
- mobile_device_target:        # e.g. "iPhone 16 Pro", or an `adb` serial; blank = the driver's default device
- mobile_test_root:            # where COMMITTED flows/specs live (Coder-owned), e.g. .maestro/
- mobile_boot_timeout: 180     # seconds for device boot + app install before reporting BLOCKED
- mobile_wdio_config:          # appium driver only, e.g. wdio.ios.conf.ts
