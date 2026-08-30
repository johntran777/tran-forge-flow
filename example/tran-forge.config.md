# Tran Forge — project configuration

<!-- Instantiated by setup.sh, which replaces {{MVN}} with the detected toolchain prefix
     (e.g. `MAVEN_OPTS= JAVA_HOME=<jdk25> <path-to>/mvn`) so every agent runs the same
     known-good Maven regardless of shell profile defaults. -->

## Project

- language: java
- build_tool: maven
- article: .claude/skills/tran-forge/constitution/article-java-maven.md
- base_branch: main
- requirements_file: requirements.txt

## Layout

- production_src: src/main/java
- unit_test_src: src/test/java
- features_dir: src/test/resources/features
- acceptance_test_src: src/test/java/com/tranforge/bowling/acceptance

## Commands

- build: {{MVN}} -q -DskipTests compile
- unit_tests: {{MVN}} -q test -Dtest='*Test,!RunCucumberTest'
- acceptance_tests: {{MVN}} -q test -Dtest=RunCucumberTest
- all_tests: {{MVN}} -q test
- coverage: {{MVN}} -q verify   # report: target/site/jacoco/ (jacoco.xml for machine reading)
- mutation_full: {{MVN}} -q test-compile org.pitest:pitest-maven:mutationCoverage
- mutation_targeted: {{MVN}} -q test-compile org.pitest:pitest-maven:mutationCoverage -DtargetClasses={classes} -DtargetTests={tests}
- mutation_report: target/pit-reports

## Thresholds

- mutation_score_min: 85
- line_coverage_min: 90

## Intake

<!-- The kata has no Jira project. Flip jira_enabled on (and set a key) when pointing the flow at a real repo. -->

- jira_enabled: false
- jira_project_key:
- jira_write_back: false

## Artifacts

- keep_requirements: true
- keep_features: true

## Review (Codex — Phases 3–5, right after the Coder)

- codex_enabled: true
- codex_model: gpt-5.5
- codex_reasoning_effort: xhigh
- codex_sandbox: read-only
- performance_budget:          # the kata is pure in-memory domain logic — nothing to budget yet

## Manual test (Phase 7 — the second human gate)

<!-- `auto` is correct here: requirements.txt asks for the score to be exposed over an HTTP endpoint, so from
     cycle 1 the kata has a REST edge and `auto` resolves to `service` (boot + curl). It falls back to
     `library` (jshell against the scoring API) for any cycle that adds no reachable edge. -->

- manual_test_mode: auto
- run_app: {{MVN}} -q spring-boot:run
- app_base_url: http://localhost:8080
- app_health_path: /actuator/health

<!-- ui_src_paths is intentionally BLANK: the kata has no UI at all — no src/main/resources, no templates, no
     static assets, no frontend build — so `auto` never resolves to browser mode and the UI guard never fires.
     Point the flow at a repo with a real frontend and fill this in to get browser coverage. -->

- ui_src_paths:
- ui_base_url:
- ui_start:
