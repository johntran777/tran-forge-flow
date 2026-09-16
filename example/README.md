# Tran Forge demo — Bowling Game kata

A tiny Java 25 / Spring Boot 4 Maven project, pre-wired so the `/tran-forge` pipeline can run
end-to-end immediately: JUnit 5 + Cucumber-JVM (acceptance), QuickTheories (property tests),
JaCoCo (coverage), PIT (mutation testing).

Bowling scoring is Uncle Bob's canonical TDD kata — `requirements.txt` stages it as four features
(open frames → spares → strikes → tenth frame), one Tran Forge cycle each, so the "merge back and
ask for the next feature" loop gets exercised too.

> Note: this demo uses the plain public `spring-boot-starter-parent` rather than a private in-house
> parent POM, so it builds anywhere without access to a private artifact repository.

## Quickstart

```bash
./setup.sh            # instantiates ../example-run (or pass a target dir)
cd ../example-run
claude
```

Then invoke `/tran-forge`. What happens:

1. **Preflight** — config read, clean tree checked, six worktrees created
   (`.worktrees/{coder,mutator,review-arch,review-security,review-perf,verify}`), toolchain + Codex smoke run.
2. **Specify** — the Specifier drafts Gherkin for Feature 1 and the pipeline stops at **Gate 1**:
   you approve (or revise) the spec.
3. **Code → Review ×3 → Mutate** — autonomous on isolated branches, handing off commit SHAs.
   The reviews are three Codex passes at `gpt-5.6-sol`/`xhigh` — design & architecture, OWASP security and
   performance — spawned together and run **in parallel**, one read-only worktree each; without the `codex`
   CLI each is reported SKIPPED, not passed. The lead waits for all three, de-duplicates their findings into
   one list, and hands it back to the Coder, which works it one finding at a time before the reviewers re-run.
4. **Manual test** — `auto` mode: `requirements.txt` asks for the score over an HTTP endpoint, so this
   resolves to `service` (boot the app, drive it with real `curl` traffic, tail the log). Cycles that
   add no reachable edge fall back to `library` (jshell against the scoring API). Either way the tester
   exercises every approved scenario by hand plus the edges the spec never pinned. The kata has no UI,
   so no browser is involved. The pipeline stops at **Gate 2**: you sign off.
5. **Cycle close** — the lead merges to `main`, asks whether to keep the requirement entry and the
   `.feature` file, presents the cycle report (tests, coverage, mutation score, review findings,
   Gherkin sensitivity per scenario, manual results), and asks for the next feature.

## Why setup.sh (instead of running in place)

`example/` lives inside the `ai-agent-flow` git repo and ships **git-less** — a nested `.git`
would confuse both repos, and demo runs would dirty the template. `setup.sh` copies the template
to a disposable directory, installs the flow into `.claude/`, bakes the detected Java 25 + modern
Maven toolchain into `tran-forge.config.md` (your shell profile's defaults may point at an older
JDK), and inits a fresh repo. Re-run it any time for a pristine demo.

## Scaffolding notes

- `RunCucumberTest` passes vacuously while there are no `.feature` files (`failIfNoTests = false`),
  so the preflight smoke is green on the virgin kata.
- `SmokeTest` exists only to prove the unit toolchain; the Coder may delete it once real
  tests exist.
- PIT excludes the `acceptance` package (Cucumber engine) and the Spring bootstrap class — killing
  mutants is the unit suite's job.
- Property testing is QuickTheories, deliberately not jqwik: jqwik ≥ 1.10.1 prints a
  prompt-injection banner into test output on every run, which is hostile to an agent-driven
  pipeline that reads build output.
