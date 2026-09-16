# Tran Forge Flow

A rigid, role-per-branch AI-agent TDD pipeline of adversarially-separated specialists. Each role works in an
isolated git worktree and hands off **commit pointers** (not diffs) down the chain, coordinated by a team
lead. There are exactly **two approval gates** — you approve the Gherkin specification before any code is
written, and you sign off the manual-test report before anything merges back. Upstream of the first gate, an
optional interactive **grilling** (Phase 0, the `grill-me` skill) forms a well-defined requirement when the
input — a `requirements.txt` entry or a **Jira ticket** — is too vague to specify from.

Three ways to start a cycle: `/tran-forge PROJ-1234` (Jira), `/tran-forge <describe the feature>` (free text),
or bare `/tran-forge` (takes the next unimplemented item from the requirements file). No requirements file
yet? Preflight asks you for a ticket or a description and creates one — it never invents a feature to
proceed.

```
                                                                    ┌── consolidated findings ──┐
                                                                    ↓                           │
                                                                          ┌─ arch ────┐
jira? ─→ requirements ─→ [GRILL] ─→ Specifier ─→ [GATE 1] ─→ Coder ─→ ────┼─ security ┼──────────┘─→ Mutator ─→ Manual test ─→ [GATE 2] ─→ merge ─→ next?
 (opt)                  (interactive,   (base)    Gherkin    (TDD +       └─ perf ────┘              (PIT +       (plan +      sign-off    (lead)
                          optional)               approved   tidy +    3 Codex reviews, spawned      sensitivity)  execute)
                                                  before      cover)   together, run in parallel
                                                  code
```

| Role                 | Discipline                                                                                          |
|----------------------|-----------------------------------------------------------------------------------------------------|
| Jira intake (lead)   | Optional: `/tran-forge PROJ-1234` pulls the ticket through the Atlassian MCP and **distils** it into a plain-text requirement entry (never Gherkin, never verbatim). Read-only on Jira by default |
| Grill (lead)         | Optional Phase 0: interviews you (`/grill-me` protocol) until a vague requirement becomes end-state behavior, edge cases, non-goals, success criteria — written back to `requirements.txt`. Always runs for a Jira ticket with open unknowns |
| Specifier            | Informal requirements → deterministic Gherkin `.feature` files; commits on base only after user approval |
| Coder                | The pipeline's **only** writer of production code. Strict TDD: failing unit test first, minimal production code second, tidy the unit you just greened, until every scenario passes — then coverage to the bar and property tests, each gap-closing test proven to fail against a deliberate break. Runs `implement` for the feature and `review-fix` for every finding that comes back, under a hard behavior-preservation protocol |
| Architecture reviewer| *(one of three reviews spawned together and run in parallel, each in its own read-only worktree)* Design & architecture audit of the cycle diff — dependency rule, ports and adapters, domain model, information hiding, precedent, SOLID — measured against the project article's own architecture rules and driven through the **Codex CLI** (`gpt-5.6-sol` @ `xhigh`), plus mechanical checks (forbidden-import grep, ArchUnit, jdeps cycles), a class-to-layer map, a public-surface list, a test-coupling review and a Gherkin-to-model audit. The pipeline's only structural check. Read-only; findings routed back to the Coder by the lead |
| Security reviewer    | Current-edition OWASP Top 10 audit of the cycle diff, same Codex reviewer pattern for an independent model's opinion, plus deterministic secret/dependency scans, a test audit for missing deny-path coverage, and a Gherkin audit for missing unauthorized-caller scenarios. Read-only; findings routed to the Coder (or, for spec gaps, the Specifier) by the lead |
| Performance reviewer | N+1s, unbounded reads, missing pagination, missing indexes, blocking IO, accidental O(n²), oversized transactions, resource leaks, over-fetching — same Codex reviewer pattern, graded against the config's performance budget, plus a measured statement count per acceptance scenario from an SQL-logged test run so N+1 findings arrive as numbers. Read-only |
| Mutator              | PIT mutation testing — kills surviving mutants by strengthening **tests only** — plus the manual **Gherkin sensitivity sweep**: break each scenario's rule, prove the scenario fails, revert |
| Manual tester        | Drives the real thing, dispatching by surface — `browser` through Playwright MCP, `mobile` on a simulator via Maestro/Detox/Appium, `service` over HTTP, `library` through the configured REPL, stacked when a change spans surfaces — exercising every scenario by hand plus the edges the spec never pinned. Refuses to pass a surface it had no way to exercise. Read-only; its report is Gate 2 |

## Layout

```
agents/                          # seven role definitions (subagent_type = filename stem)
skills/tran-forge/SKILL.md      # the orchestrator — invoke as /tran-forge
skills/tran-forge/constitution/ # discipline.md, workflow.md, article-java-maven.md
skills/tran-forge/config-template.md
skills/grill-me/SKILL.md         # Phase 0 requirements grilling — also standalone as /grill-me
skills/tran-forge-history/       # post-cycle record — invoke as /tran-forge-history [KEY-123]
example/                         # Bowling Game kata demo (Java 25 / Spring Boot 4)
```

`tran-forge-history` runs **after** a cycle (or mid-flight) and writes nothing into the pipeline. It
reconstructs the run from the evidence it left — the base branch's commit ledger, the role branch heads, the
Gherkin artifacts, the PIT and surefire reports, the requirements file's decision entries — and recovers the
**verbatim Codex review prompts** from `~/.codex/sessions/*/rollout-*.jsonl`, matching each session to its
reviewer by working directory. Output is one self-contained local HTML page with an interactive pipeline
diagram. Every verification stage is attributed with its tooling — the Codex model and effort for each
review, the PIT invocation, survivor dispositions and sensitivity sweep for the Mutator, the mode, driver,
target and counts for each manual-test surface — read from the cycle ledger. Its two standing rules:
fabricate nothing (an unrecoverable number is reported as unrecoverable, in the document, where the number
would have been), and record the failures — including the orchestrator's own wrong calls — as prominently
as the metrics.

Six worktrees: `.worktrees/coder` and `.worktrees/mutator` write; `.worktrees/review-arch`,
`.worktrees/review-security`, `.worktrees/review-perf` and `.worktrees/verify` are **read-only**. Those four
never commit — each moves its own branch to the SHA it's handed with `git merge --ff-only` and only reads. A
failed fast-forward means something committed on that branch, which is itself an escalation.

The three reviewers get **one tree each** rather than sharing, because they run concurrently: git cannot check
one branch out twice, and three agents cannot safely share an index or a scratch directory. They are the only
roles in the pipeline spawned together — everything else consumes the previous stage's commit and so must be
serial.

## Install

```bash
# per-project install
cp -R agents skills "$YOUR_PROJECT/.claude/"

# or install once for every repo
cp agents/tran-forge-*.md ~/.claude/agents/
cp -R skills/tran-forge skills/grill-me ~/.claude/skills/
```

Either works. Preflight resolves which one is in play and passes the constitution's absolute path to every
agent, so a user-level install needs no per-repo copy — only a `tran-forge.config.md` at each target repo's
root. A project-level install wins when both exist.

Then:

1. Ensure `.claude/settings.json` has `"env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}`.
2. Create `tran-forge.config.md` at the repo root (copy `skills/tran-forge/config-template.md`;
   `/tran-forge` offers to do this for you). Java 25 / Spring Boot 4 / Maven is the default stack —
   override by editing the config commands and/or pointing `article:` at your own stack article.
   Also set the `Intake` / `Artifacts` / `Review` / `Manual test` blocks for your project.
3. For the three review phases (3–5), have the [Codex CLI](https://github.com/openai/codex) on `PATH` and
   logged in (`codex --version`). No Codex → set `codex_enabled: false`, or they are reported **SKIPPED** (never
   as passed). For Jira intake, connect the Atlassian MCP; without it the flow asks you to paste the ticket.
4. Restart Claude Code, run `/tran-forge` — or `/tran-forge PROJ-1234` to start from a ticket.

## Demo

```bash
cd example && ./setup.sh    # instantiates ../example-run with a fresh git repo + .claude install
cd ../example-run && claude # then: /tran-forge
```

See `example/README.md` for the walkthrough.

## Deviations from the house defaults — read this

- **Agents commit.** The house rule ("no commits without user confirmation") is deliberately relaxed:
  commit-per-role-branch IS the handoff mechanism. Scope: Coder/Mutator commit only on their
  own `tran-forge-*` branches; the Specifier commits only `.feature` files on base, only after the user
  approves at the gate; the three reviewers and the manual tester commit **nothing at all**; the lead performs
  the cycle-close merge, the cycle-ledger commit (`<ledger_dir>/`, the durable record of verdicts, findings
  and gate decisions that lets the next cycle start in a fresh context) and any artifact-retention follow-up
  commit.
- **No agent ever pushes.** Pushing remains exclusively a user decision after the skill ends.
- **Two approval gates, not per-phase gates.** Gate 1: Gherkin approval, before any code exists. Gate 2: the
  manual-test report, before anything merges back. Code → Review ×3 (looping back to the Coder) → Mutate run autonomously between
  them; genuine ambiguity still stops the pipeline, and so does any review Blocker whose fix would change
  observable behavior (that's a spec change, which belongs to the Specifier behind Gate 1). The Phase 0
  grilling adds an interactive conversation *before* the cycle when a requirement needs forming.
- **Jira stays read-only** unless the config sets `jira_write_back: true` *and* you confirm at cycle close.
  The flow reads a ticket; it never silently comments on or transitions one.
- **Codex runs with `-s read-only`**, always — overriding whatever `~/.codex/config.toml` defaults to. The
  reviewers must not be able to modify the repo, and neither must the tool they drive.

## Known limitations

- Java/Maven is the only stack article shipped; other stacks need their own article + config commands.
- PIT excludes the Cucumber suite by design (its per-test coverage mapping doesn't work through the
  Cucumber engine) — mutation killing rests on the unit suite, which is why the Coder keeps unit and
  acceptance tests strictly separate. The acceptance suite is instead graded by the Mutator's **Gherkin
  sensitivity sweep**: for every scenario, break the rule it states, prove that scenario fails, revert.
  Deliberately *not* solved by pointing PIT at Cucumber — that path is slow, flaky, and measures out as
  a dead end.
- Property testing uses QuickTheories, not jqwik: jqwik ≥ 1.10.1 prints a prompt-injection banner into
  test output on every run — hostile to an agent-driven pipeline that reads build output.
- The Codex model slug (`gpt-5.6-sol`) is pinned in the config, not discovered. Codex's model list moves; check
  `~/.codex/models_cache.json` and bump the config when it does.
- The manual tester's `service` mode assumes a locally bootable app. Against a shared or remote target it
  stops and asks before every write — it is not a stage-smoke tool.
- **Phase 7 dispatches by surface.** Web → `browser` mode through Playwright MCP (add
  `{"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}}` to `.mcp.json`), asserting on the
  accessibility snapshot. Native → `mobile` mode, which builds the real binary and drives it on a
  simulator/emulator via `mobile_driver` (`maestro` recommended: plain CLI, no MCP dependency, implicit waits,
  and `--debug-output` gives both a hierarchy dump to assert on and screenshots for the human; `detox` and
  `appium` also supported). Network edge → `service` mode over HTTP. Neither → `library` mode through
  `library_repl`. Modes stack, so code shared by a web shell and a native app is exercised in both.
- **Native mobile needs setting up before it works.** `mobile_driver` ships as `none`, and the mode also needs
  `mobile_build`, `mobile_app_binary` and a reachable device. Until then a native diff is reported BLOCKED, never
  approximated — browser device emulation covers *responsive web* only, being a resized browser rather than a
  native iOS/Android/React Native/Flutter app.
- **Phases 1–6 remain JVM-shaped** (PIT, JaCoCo, Cucumber-JVM, a Java/Spring article). A `mobile` Phase 7 does
  not by itself make the flow runnable on a JS/TS mobile repo: that additionally needs a JS Gherkin runner, Jest
  coverage, and Stryker in place of PIT.
- The surface guard depends on `ui_src_paths` / `mobile_src_paths` being set. Blank means that arm can never fire
  — correct for a repo without that surface, dangerous for one that has it, so `/tran-forge` preflight warns when
  it finds web assets or a native app alongside a blank key.
