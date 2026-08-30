---
name: tran-forge
description: "User-invoked TDD pipeline skill (`/tran-forge`). Use to drive one feature through the Tran Forge cycle — optional Jira intake → Grilling (Phase 0: refine a vague requirement via /grill-me, interactive, skipped when already well-formed) → Specifier (Gherkin, user-approved) → Coder (strict TDD, tidy-as-you-go, coverage to the bar) → three Codex reviews (design/architecture, then security/OWASP, then performance) whose findings loop straight back to the Coder → Mutator (PIT mutation testing + Gherkin sensitivity sweep) → Manual test (user sign-off) — with each role committing on an isolated git-worktree branch and handing off commit SHAs through the team lead, then merging back to the base branch, asking whether to keep the requirement/Gherkin artifacts, and offering the next feature. Requires a tran-forge.config.md in the target repo (Java 25 / Spring Boot 4 / Maven default; overridable)."
allowed-tools: Bash(git:*), Bash(mvn:*), Bash(codex:*), Bash(mkdir:*), Bash(cp:*), Bash(cat:*), Bash(ls:*), Bash(find:*), Bash(grep:*)
user-invocable: true
---

# Tran Forge

A rigid role-per-branch TDD pipeline for Claude Code, where each role works in an
isolated git worktree and hands off **commit pointers** (not diffs) down the chain, all routed through the team
lead — you, the main thread.

There are exactly **two approval gates**: the user approves the Gherkin specification before any code is
written, and signs off the manual-test report before anything merges back. Upstream of the first gate, when the
chosen requirement is too vague to specify from (a raw Jira ticket almost always is), an interactive
**grilling** (Phase 0, via the `grill-me` skill) forms a well-defined requirement first — the pipeline's
verification stack proves the code matches the spec, so the spec must match the user's intent. Between the two
gates, Coder → Review ×3 → Mutator run autonomously.

```
                                                              ┌── consolidated findings ──┐
                                                              ↓                           │
                                                                    ┌─ arch ────┐
jira? ─→ requirements ─→ [GRILL] ─→ Specifier ─→ [GATE 1] ─→ Coder ─┼─ security ┼──────────┘─→ Mutator ─→ Manual test ─→ [GATE 2] ─→ merge ─→ next?
 (opt)                  (interactive,   (base)    Gherkin    (TDD +  └─ perf ────┘             (PIT +        (plan +      sign-off    (lead)
                          optional)               approved   tidy +   3 Codex reviews,          sensitivity)  execute)
                                                  before      cover)  spawned together,
                                                  code               run in parallel
```

**The Coder is the pipeline's only writer of production code, and every review finding loops back to it.**
That is the pipeline's spine: one role writes, three independent reviews grade what it wrote, corrections go
back to the same role and are re-reviewed. Nothing reaches the Mutator that a review has not seen — with two
bounded, deliberate exceptions: fixes for Mutator escalations (Phase 6) and manual-test failures (Phase 7)
land after the review stage, and get a targeted re-review only when the rule in those phases calls for one.

The three reviews are **separate agents with separate beats, spawned together and run in parallel**: design &
architecture (Clean Architecture, ports/adapters, SOLID), security (OWASP Top 10), and performance. Splitting
them is deliberate — one reviewer asked for "any problems" returns the shallowest finding in each category,
and a security pass mixed into a design pass reliably loses to whichever the model finds more interesting.
Running them concurrently is safe because they all read the same commit and none of them writes: each gets its
own read-only worktree, and the lead waits for all three before routing anything back.

There is deliberately **no separate Refactorer role**. Local tidiness belongs to the Coder in the third beat of
its own TDD loop (rename, extract, collapse — while it still remembers why), and cross-cutting restructuring
arrives as a *finding* from the design & architecture review rather than as one agent's unreviewed taste. See
"Why no Refactorer" at the end.

## Inputs

Invoked as `/tran-forge`, optionally with a Jira ticket reference, a feature description, and/or a target repo
path.

- **Target repo**: the path argument if given, else `$CLAUDE_PROJECT_DIR`.
- **Jira ticket**: an argument matching `[A-Z][A-Z0-9]+-\d+` (e.g. `PROJ-1234`), a bare number when the config
  sets `jira_project_key`, or an Atlassian issue URL (`.../browse/KEY-123`). Handled in Preflight step 8.
- **Feature**: the free-text argument if given, else the Jira ticket, else the first unimplemented item in the
  config's `requirements_file`. If several candidates exist and no argument was given, ask the user which
  feature this cycle covers. If there is **no** requirements file, it is empty, or nothing in it is
  unimplemented, Preflight 9 asks for a Jira ticket or a plain-text requirement — the flow never invents one.

One invocation drives **one feature** through the whole cycle, then offers the next.

## Prime directive — token discipline

You are the lead, and one more thing about this pipeline is rigid: **your context is its scarcest resource.**
Every role's report lands here, and every routing decision — the dedupe across three reviews, the
contradiction calls, which Blockers are `needs-spec-change` — is made here. The lead is therefore the first
context to degrade and the worst one to lose.

**The budget is `context_budget_tokens` (default 100000).** Every role, and you, are designed to finish
inside it. It is a design ceiling, not a runtime meter: you cannot query your own context size, so **do not
claim to measure it** — govern it with the structural proxies below, which are what actually keep a context
under the line.

- **One cycle per context** — the primary proxy, because one full cycle deposits roughly half to all of the
  budget here. The Phase 8 ledger makes the next cycle lossless in a fresh session, so recommend that route
  at "next feature?" rather than looping in-place.
- **Never read production source or diffs yourself.** You read reports; the roles read code. The one
  exception is diff *paths* (`git diff --name-only`) for the checks this file explicitly assigns you.
- **Pass paths, not contents.** Spawn briefs carry absolute paths and SHAs — never pasted file bodies,
  report bodies, or diff hunks. Agents pull; you do not push.
- **Pipe build output.** Any build/test command you run yourself goes through
  `2>&1 | tail -40` after grepping the `Tests run:` / `BUILD` counters. The full log is for a red you are
  actively diagnosing, nothing else.
- **Enforce `report_max_lines`** (default 60): an oversized completion report goes back to its author to
  compress — with one carve-out: findings/verdict **tables are never truncated**. Prose is what compresses;
  a cut finding row is unrecoverable downstream (the dedupe, the cycle report and `/tran-forge-history` all
  consume those rows).
- **Every role spawn is fresh, and re-spawning is the cheap fix.** A role's context is disposable; the
  worktree, branch and ledger hold the state. When a role has been round-tripped several times and its
  replies are drifting, re-spawn it with the last handoff SHA rather than pressing on.

Carry `context_budget_tokens` into every spawn brief so each role can size its own reading and reporting
against the same number.

## Preflight

Do these in order. **Stop and ask the user on any failure — never auto-fix the user's repo state.**

1. **Env** — Agent Teams must be enabled (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`). If not, stop and tell the
   user to add it to `.claude/settings.json` → `env` and restart.
2. **Target repo** — verify it is a git repo (`git rev-parse --git-dir`).
2b. **Locate the install — `<constitution_dir>`.** This flow can be installed per-project or for the whole
   user, and every agent needs the constitution's **absolute** path in its brief. Resolve it once, here:
   - `<repo>/.claude/skills/tran-forge/constitution/` exists → use it (a project-level install wins).
   - Else `~/.claude/skills/tran-forge/constitution/` → use that (user-level install).
   - Neither → STOP: the flow is not installed where the agents can read it. Tell the user to copy `agents/`
     and `skills/` into either location.

   Confirm `discipline.md` and `workflow.md` are both there before continuing, and carry the resolved absolute
   path into **every** spawn brief. Never pass a relative `.claude/...` path: subagents resolve it against the
   working directory, which for most roles is a worktree, not the main checkout.
3. **Config** — read `tran-forge.config.md` at the repo root.
   If it does not exist, offer to create one from
   `.claude/skills/tran-forge/config-template.md` (Java 25 / Spring Boot 4 / Maven defaults) and let the user
   confirm or edit before continuing. Read the article file its `article:` key points at. Resolve
   `base_branch`, the `Intake` / `Artifacts` / `Review` / `Manual test` blocks, and the thresholds.

   **The `Token budgets` block is optional — every key has a built-in default.** A config written before the
   block existed is complete as it stands: resolve each missing key to
   the default below, mention in one line which ones you defaulted, and **never** stop, warn, or offer to
   rewrite the config over an absent budget key.

   | Key                     | Default        | What it governs                                              |
   |-------------------------|----------------|--------------------------------------------------------------|
   | `context_budget_tokens` | `100000`       | The per-context ceiling this flow is designed around (below) |
   | `report_max_lines`      | `60`           | Prose cap on a role's completion report; tables exempt       |
   | `ledger_dir`            | `.tran-forge`  | Where the cycle ledger lives (started after Gate 1)         |

   Resolve `ledger_dir` to an absolute path now and `mkdir -p` it when the ledger starts (Phase 1 step 5,
   right after Gate 1), not here — nothing under it may exist before the Specifier's clean-tree check has run.
4. **Clean tree** — `git status --porcelain` on the main checkout must be empty. Dirty → STOP and ask: the
   Specifier commits on base and the cycle-close merge lands on base; a dirty base makes both unsafe. Never
   stash silently. One special case: if the only dirt is an in-progress ledger under `<ledger_dir>`, that is
   an interrupted cycle — see "Resuming an interrupted cycle" below.
5. **Worktrees — you create them, not the agents.** Run `git worktree prune`, then for each of
   coder / mutator / verify / **review-arch / review-security / review-perf**:
   - `.worktrees/<role>` exists and is on `tran-forge-<role>` → reuse it.
   - Branch `tran-forge-<role>` exists but no worktree → `git worktree add .worktrees/<role> tran-forge-<role>`.
   - Neither exists → `git worktree add .worktrees/<role> -b tran-forge-<role>`.

   **Then check every reused worktree, not only the main checkout:** `git status --porcelain` in each must be
   clean — a crashed earlier run leaves uncommitted debris that the next role would otherwise merge into.
   Dirty → STOP and show the user what is there; never clean it yourself. A worktree that exists but sits
   detached, or on some branch other than `tran-forge-<role>`, is the same case: STOP and ask — never check out,
   reset, or repair it silently.

   Every agent verifies its branch name against what its brief says, so a mismatch stops the pipeline
   rather than corrupting it.

   Six trees, of which **four are read-only** (they never commit; they move their branch with
   `git merge --ff-only <sha>` and only read — see `constitution/workflow.md` → Topology):

   | Tree                        | Branch                        | Used by                        |
   |-----------------------------|-------------------------------|--------------------------------|
   | `.worktrees/coder`          | `tran-forge-coder`           | Coder (writes)                 |
   | `.worktrees/mutator`        | `tran-forge-mutator`         | Mutator (writes tests only)    |
   | `.worktrees/review-arch`    | `tran-forge-review-arch`     | Architecture reviewer (RO)     |
   | `.worktrees/review-security`| `tran-forge-review-security` | Security reviewer (RO)         |
   | `.worktrees/review-perf`    | `tran-forge-review-perf`     | Performance reviewer (RO)      |
   | `.worktrees/verify`         | `tran-forge-verify`          | Manual tester (RO)             |

   **The three reviewers get one tree each because they run concurrently** (Phases 3–5), and git allows a
   branch to be checked out in only one worktree at a time. Sharing one tree would also mean three agents
   contending for the same index lock and overwriting each other's `cycle.diff`. The manual tester runs alone,
   later, so it keeps `.worktrees/verify` to itself.

   Then append `.worktrees/` to `.git/info/exclude` if not already there (do NOT edit the user's `.gitignore`).
6. **Toolchain smoke** — run the config's `all_tests` command once in the main checkout. Must be green before
   the cycle starts. Red → stop and surface the output.
7. **External-tool smoke** — the phases that depend on tools outside the build:
   - **Codex** (skip when `codex_enabled: false`) — `codex --version` must succeed and the configured
     `codex_model` must exist. Missing binary or unknown model → tell the user, and offer to either fix it or
     run this cycle with **all three Codex review phases** skipped (a skipped review is reported as skipped,
     never as passed). One smoke check covers all three; they share the binary and the model.
   - **UI detection** — if `ui_src_paths` is blank but the repo plainly contains UI assets (templates,
     `static/`, `*.tsx`/`*.jsx`/`*.vue`/`*.svelte`, a frontend `package.json`), say so now and offer to fill the
     key in. A blank `ui_src_paths` means the web arm of the surface guard can never fire, so a silent blank in a repo that *has* a
     UI is the one configuration that can produce a confident "all pass" over an unlooked-at screen.
   - If `ui_src_paths` is set, confirm Playwright MCP is reachable (`ToolSearch("+playwright browser")`). Not
     reachable → tell the user now, not at Phase 7, so they can connect it or accept a BLOCKED web verdict.
   - **Native detection** — if `mobile_src_paths` is blank but the repo plainly contains a native app (`ios/`,
     `android/`, an RN/Expo/Flutter manifest), say so and offer to fill the key in. Same failure mode as a blank
     `ui_src_paths`: blank means the native arm of the Phase 7 guard can never fire.
   - If `mobile_src_paths` is set and `mobile_driver` is not `none`, smoke the whole native chain — the driver
     binary (`maestro --version` / `detox --version` / `npx appium --version`), a reachable device
     (`xcrun simctl list devices booted` / `adb devices`), and a non-blank `mobile_build` plus
     `mobile_app_binary`. A driver with no build command cannot produce anything to test. Anything missing →
     tell the user now so they can fix it or accept a BLOCKED native verdict, rather than discovering it after
     the Coder, three reviews and the Mutator have already run.
8. **Jira intake** (only when a ticket reference was given, or when the user asks for one) — see below.
9. **Feature selection.** Resolve exactly **one** feature for this cycle, in this order:

   1. **An argument was given** — free text, or a Jira key (which routed through Preflight 8) → that is the
      feature. No prompt.
   2. **`requirements_file` has unimplemented items** — exactly one → take it. Several → **ask the user which
      one this cycle covers**; never pick for them when the list is ambiguous.
   3. **`requirements_file` is missing, empty, or has nothing unimplemented → STOP and ask the user.** This is
      the one point where the flow asks for a requirement instead of reading one. Ask for either:

      - a **Jira ticket** — `KEY-123`, a bare number when the config sets `jira_project_key`, or a browse URL;
        or
      - a **plain-text description** of the requirement — what changes for the user, in a sentence or two.

      A **Jira answer** → run **Preflight 8** now, then continue here.
      A **free-text answer** → create `requirements_file` if it does not exist (at the path the config names)
      and seed it with exactly this, uncommitted:

      ```markdown
      ## <short title drawn from the user's words>

      <the user's description, verbatim>
      ```

      **Write nothing else.** No Gherkin, no invented acceptance criteria, no expansion of one sentence into a
      spec — Phase 0 grills it into shape and the Specifier formalizes it, and anything you add here is an
      unreviewed guess the user never approved. A requirement that arrives this way has by definition not been
      through the Phase 0 bar, so **the grilling runs** unless the user explicitly says to skip it.

      **Never invent a feature to proceed**, and never fall back to "the first thing in the repo that looks
      unfinished." No requirement means no cycle: if the user declines to give one, stop and say so.

   Then restate the chosen feature to the user in one line and proceed to Phase 0.

### Preflight 8 — Jira intake

The pipeline consumes plain-text requirements. A Jira ticket is an *input to* that text, never a substitute for
it.

1. **Resolve the key.** Normalize the argument to `KEY-123` (prepend `jira_project_key` for a bare number).
2. **Load the MCP tool**, then fetch:

   ```
   ToolSearch("select:mcp__claude_ai_Atlassian__getJiraIssue")
   mcp__claude_ai_Atlassian__getJiraIssue({issueIdOrKey: "KEY-123", responseContentFormat: "markdown"})
   ```

   Read summary, description, acceptance criteria, issue type, and linked/parent issues if the description
   depends on them. If the ticket's comments carry requirement detail, fetch them too
   (`mcp__claude_ai_Atlassian__getJiraIssue` with comments, or `...__fetch` on the issue URL).
3. **MCP unavailable** (not connected, auth expired, tool not found) → STOP and offer the user two options: ask
   them to paste the ticket body into the conversation, or continue from a free-text feature description. Never
   invent ticket contents, and never proceed on the key alone.
4. **Distill, don't transcribe.** Append an entry to the config's `requirements_file` — **creating the file
   if it does not exist** — uncommitted for now:

   ```markdown
   ## KEY-123 — <ticket summary>

   Source: Jira KEY-123 (fetched <date>)

   <intent in 2–4 plain sentences: what changes for the user, and why>

   Acceptance criteria (from the ticket):
   - <verbatim bullets>

   Unknowns (to resolve in grilling):
   - <numbered list of everything the ticket leaves open>
   ```

   **Plain text only — no Gherkin.** Formalizing is the Specifier's job.
5. **Grilling is the default for Jira intake.** A ticket that clears the Phase 0 bar (purpose, observable
   end-state behavior, edge cases, non-goals, success criteria) is rare; if the `Unknowns` list is non-empty,
   Phase 0 runs.
6. **The ticket key becomes this cycle's artifact prefix**: feature file `<key>-<slug>.feature`, and every
   commit message in the cycle is prefixed `KEY-123: `.
7. **Jira is read-only by default.** Do not comment on, transition, assign, or otherwise write to the ticket
   unless the config sets `jira_write_back: true` **and** the user asks at cycle close. Posting to Jira is an
   outward-facing action — it needs explicit per-cycle confirmation even then.

## Phase 0 — Refine the requirement (the grilling; interactive, skipped when well-formed)

The pipeline's verification stack proves the code matches the spec — it cannot prove the spec matches the
user's intent. That is this phase's job. Run it in the main thread, before the team exists:

1. Judge the chosen feature's entry in `requirements_file` against this bar: purpose, observable end-state
   behavior, edge cases, non-goals, and success criteria — concrete enough that the Specifier could write
   deterministic Gherkin without inventing a single interpretation.
2. **Well-formed** (kata-style entries usually are) → say so in one line and proceed to Phase 1. If the user
   explicitly asked to be grilled, run the grilling anyway; if they explicitly said to skip it, skip it.
   A Jira-derived entry with a non-empty `Unknowns` list is **never** treated as well-formed.
3. **Vague, one-line, or contradictory** → Read `.claude/skills/grill-me/SKILL.md` and execute its protocol
   now, topic = this feature. Interview until the played-back design concept is explicitly confirmed. Seed the
   question list with the entry's `Unknowns`.
4. Rewrite the feature's entry in `requirements_file`: plain-text end-state behavior, edge cases, non-goals,
   success criteria. Keep the `Source: Jira KEY-123` line when there is one. **No Gherkin syntax** —
   formalizing is the Specifier's job; don't pre-chew its work.
5. Show the rewritten entry to the user; on their approval commit it on base
   (`[KEY-123: ]Requirements: <feature> (refined by grilling)`) so the tree is clean again before the Specifier
   starts. **`git add` the requirements file explicitly** — when this cycle created it (Preflight 9 route 3, or
   a first Jira intake) it is untracked, and a plain `git commit -a` would leave it out and then fail the clean
   tree check at cycle close. Commit the entry here even when the grilling was skipped — Jira-derived or seeded from a
   free-text answer at Preflight 9 alike; an entry that reaches Phase 1 uncommitted trips the Specifier's
   clean-tree check and wedges the cycle. The retention gate at cycle close decides whether it stays.

This phase refines only the one feature this cycle covers — never the whole requirements file.

## Team orchestration

```
TeamCreate({team_name: "tran-forge-<repo-slug>", description: "Tran Forge TDD cycle: <feature>"})
```

- The main thread is the **team lead**: it owns the task list, relays every handoff SHA, runs the two human
  gates, performs the cycle-close merge, and never does role work itself.
- Create the phase tasks up front via `TaskCreate`: Specify / Code / Review-architecture / Review-security /
  Review-performance / Mutate / Manual-test / Merge-back.
- **Spawn one agent at a time, strictly sequentially — with exactly one exception: the three reviews at
  Phases 3–5 are spawned together, in a single message, and run concurrently.** Everything else in this
  pipeline is serial because each stage consumes the previous stage's commit; the three reviews consume the
  *same* commit and produce no commit, so nothing orders them. Use the dedicated `subagent_type`s
  (`tran-forge-specifier`, `tran-forge-coder`, `tran-forge-architecture-reviewer`,
  `tran-forge-security-reviewer`, `tran-forge-performance-reviewer`, `tran-forge-mutator`,
  `tran-forge-manual-tester`), never `general-purpose`. No `model:` on the spawn call — the agent files pin it.

| Order | Phase              | Agent                              | Works in                | Gate                                        |
|-------|--------------------|------------------------------------|-------------------------|---------------------------------------------|
| —     | Jira intake        | team lead (you)                    | main checkout (base)    | optional; user pastes the ticket if no MCP  |
| 0     | Grill              | team lead (you) + user             | main checkout (base)    | interactive; skipped when already well-formed |
| 1     | Specify            | `tran-forge-specifier`            | main checkout (base)    | **GATE 1 — USER approves Gherkin**          |
| 2     | Code               | `tran-forge-coder` (`implement`)   | `.worktrees/coder`      | autonomous (lead sanity-check)              |
| 3 ┐   | Review — design/arch | `tran-forge-architecture-reviewer` | `.worktrees/review-arch` (RO)| autonomous ┐ spawned together, |
| 4 ├─╫ | Review — security  | `tran-forge-security-reviewer`    | `.worktrees/review-security` (RO)| run concurrently; all three |
| 5 ┘   | Review — perf      | `tran-forge-performance-reviewer` | `.worktrees/review-perf` (RO)| ┘ consolidated → Coder |
| 6     | Mutate             | `tran-forge-mutator`               | `.worktrees/mutator`    | autonomous (lead sanity-check)              |
| 7     | Manual test        | `tran-forge-manual-tester`        | `.worktrees/verify` (RO)| **GATE 2 — USER signs off the report**      |
| 8     | Merge + retention  | team lead (you)                    | main checkout (base)    | cycle report; keep-artifacts question       |

Every Coder spawn names a **mode**: `implement` at Phase 2, `review-fix` for every finding round-trip
thereafter. A `review-fix` brief carries exactly ONE finding — never a batch — plus its source, its
`behavior-preserving` / `needs-spec-change` flag, and the SHA to merge.

**Every `review-fix` is a fresh spawn.** Never `SendMessage` the finished `implement`-mode Coder into fixing:
that drags its entire TDD transcript — every red/green iteration, every build log — into the fix pass as dead
context. The worktree and branch carry all the state a fix needs; a fresh spawn starts from the brief, the
constitution and a green baseline, which is the smart-zone shape.

### Spawn briefs — required blocks

Every `Agent({...})` prompt must include: the absolute paths (target repo main checkout, the agent's working
directory, the config file, **and `<constitution_dir>` from Preflight 2b**), the feature name (with the Jira
key when there is one), the incoming handoff SHA (phases 2–7), the spec SHA (phases 3–7, for the differential
diff), the Coder's mode when spawning the Coder, the resolved `context_budget_tokens` and `report_max_lines`,
and — for the three reviewers **and the manual tester** — its own scratch directory, plus this block
verbatim:

```
HARD RULES (Tran Forge):
- You MAY git commit, but ONLY on your own branch (<branch>) in your own working dir (<abs path>). This is
  the one sanctioned deviation from the house no-commit default — commit-per-role-branch is the handoff
  mechanism. (Specifier: spec files only, on the base branch, only after the lead relays user approval.
  Architecture reviewer / security reviewer / performance reviewer / manual tester: read-only — you commit
  NOTHING, ever.)
- NEVER git push. NEVER touch any other branch, except `git merge <handoff-sha>` into your own.
- On ambiguity or merge conflict: git merge --abort if mid-merge, then stop and report to the team lead.
  Do not guess.
- Context budget: <context_budget_tokens> tokens for your whole run; keep your report's prose under
  <report_max_lines> lines. Findings/verdict TABLES are exempt — never drop a row to fit. Read what the
  brief points you at, not the repo at large; grep large generated files, never Read them whole.
- When done, mark your task complete via TaskUpdate — the completion comment must include your 10-char
  handoff SHA (git rev-parse --short=10 HEAD) — and stand by.
- Before reporting done, re-read this brief and verify every item is covered.
```

**Scratch directories are yours to create, and they never live in the repo.** `mkdir -p` one per role per
cycle outside the repository — under the session's scratch directory or `$TMPDIR` — and pass its absolute path
in the brief. Never place one inside a worktree or the main checkout: every tree in this pipeline is expected
to stay clean, and a scratch directory inside one dirties exactly the state the clean-tree checks protect.

## Phase 1 — Specify (GATE 1)

1. Spawn `tran-forge-specifier` with the feature brief — pointing at the feature's (Phase-0-refined, when
   the grilling ran) entry in `requirements_file`, plus the Jira key when there is one (for the feature-file
   name and commit prefix).
2. **Present the Gherkin to the user verbatim** along with any open questions **and the Specifier's
   cross-cutting-decisions block** (timezone/"today", i18n, null/empty, HTTP error codes, ordering/pagination).
   These are decisions that otherwise get silently locked in by the first implementation choice — the user
   rules on them here, at this gate, not after the code exists. Ask: approve, or request changes?
3. Changes requested → `SendMessage` the specifier the feedback; it revises and re-reports. Loop.
4. Approved → `SendMessage` "approved — commit". The specifier commits (spec files only, message ending
   `By Specifier.`) and reports **`SHA_spec`**.
5. **Start the cycle ledger now.** `mkdir -p <ledger_dir>` and open `<ledger_dir>/<key-lowercase-or-slug>.md`
   with the feature, Jira key and `SHA_spec`. From here on, append a short entry the moment each phase
   completes — handoff SHA, verdict line, and any call you made. The file stays **uncommitted** until Phase 8
   finalizes and commits it; until then it is what makes a dead session resumable (see "Resuming an
   interrupted cycle"). Do not create it before Gate 1 — the Specifier's clean-tree check runs first.

## Phase 2 — Code (autonomous)

Spawn `tran-forge-coder` in **`implement`** mode with `SHA_spec`. It merges, TDD-loops until every scenario
and the full unit suite pass — tidying each unit as it greens it, carrying coverage to `line_coverage_min`,
adding property tests where an invariant beats examples — commits, and reports **`SHA_code`** + test counts.
Sanity-check the report and proceed without asking the user:

- All scenarios passing? Any escalations?
- **Coverage at the bar** and **coverage tests red-phased** — the Coder must report each gap-closing test as
  proven to fail against a deliberate break, then reverted. A missing red phase means tests of unknown value;
  `SendMessage` it to do the experiment before you move on. This is the checkpoint that keeps weak tests from
  reaching the Mutator as manufactured work.
- **Mutation blind spots covered** — PIT can't see them, so this is the only checkpoint: does each new/changed
  repository `@Query` have a DB-integration test, and each new endpoint a controller test + acceptance
  scenario? (See the Coder's "Blind-spot tests" report line.) If the feature touched a query or endpoint and
  the corresponding test is missing, `SendMessage` the coder to add it before Phase 3 — don't let it slide to
  the Mutator, which cannot write query/production code to compensate.
- **Tidying stayed in scope** — the "Tidying applied" lines should be renames, extractions and collapses
  within units greened this cycle. A module-scale restructuring listed there is out of the Coder's remit:
  note it and make sure the architecture review sees it.

Escalations you can't resolve mechanically → surface to the user (this suspends the autonomous run — genuine
ambiguity beats a wrong guess).

## Phases 3–5 — Codex reviews: design/architecture, security, performance (parallel, autonomous)

**Three** external reviews of the code the Coder just wrote, each with its own beat, all run through the Codex
CLI at the config's `codex_model` / `codex_reasoning_effort` (default `gpt-5.5` at `xhigh`). Codex reads a
*different* model's opinion into the pipeline — that independence is the point, so relay its findings without
editorializing.

They are split into three narrow briefs rather than merged into one because a single reviewer asked to find
"any problems" returns the shallowest finding in each category and then stops. Three briefs, three fresh
contexts, one beat each.

### Spawn all three at once

**Put all three `Agent(...)` calls in a single message.** They are the one concurrent step in this pipeline:
they consume the same commit, they write nothing, and no ordering exists between them. Wall-clock for the
review stage becomes the slowest single review rather than the sum of three.

Each brief carries `SHA_code` + `SHA_spec`, and two things that **must differ per reviewer or they corrupt
each other**:

1. **Its own worktree** — `.worktrees/review-arch` / `review-security` / `review-perf`, on the matching
   `tran-forge-review-*` branch. Never point two reviewers at one tree: they would contend for the git index
   lock, and a branch cannot be checked out twice anyway.
2. **Its own scratch directory** — each writes `cycle.diff` and its Codex `-o` output file there. A shared
   scratch dir means three agents overwriting one `cycle.diff` mid-read.

Expect the runs to be individually slower than they would be alone — three `xhigh` Codex runs contend for CPU
and API throughput. The trade is deliberate: total wall-clock still drops, and none of them can corrupt
another's inputs.

### Phase 3 — Design & architecture review

`tran-forge-architecture-reviewer` reviews the design against the project article's **Architecture rules**
section plus Clean Architecture and SOLID: dependency rule, ports and adapters, information hiding, boundaries.

This is the pipeline's **only** structural check. The Coder tidies what it greens but is barred from
cross-cutting restructuring precisely so that module-scale change is reviewed rather than improvised — which
means anything this phase misses reaches the base branch unexamined. Read its report properly; it is not a
formality.

### Phase 4 — Security review (OWASP Top 10)

`tran-forge-security-reviewer` runs the OWASP Top 10 review — access control, crypto, injection, insecure
design, misconfiguration, vulnerable dependencies, auth, deserialization, logging, SSRF.

### Phase 5 — Performance review

`tran-forge-performance-reviewer` hunts what small fixtures hide — N+1 queries, unbounded reads, missing
pagination, blocking IO on request threads, accidental O(n²), transaction scope.

### Wait for all three, then consolidate

Do **not** route anything to the Coder while a review is still running — a fix would move the code underneath
a reviewer that is still reading it, and its report would describe a commit that no longer exists. Wait for
all three to complete (or fail), then build one consolidated finding list:

1. **Dedupe across reports.** Running blind to each other, the three reviewers will sometimes raise the same
   defect in their own vocabulary — an unbounded query is a performance finding *and* a resource-exhaustion
   security finding; a leaked entity is an information-hiding finding *and* a mass-assignment one. Merge those
   into a single entry naming both reviewers, and say in the cycle report how many you merged. Sending the
   Coder the same defect three times wastes three round-trips and invites three conflicting fixes.
2. **Rank**: all Blockers first (needs-spec-change ones separated out — those stop for the user), then
   Should-fix worth doing, then the rest for the report.
3. **Resolve contradictions before dispatching.** Two reviewers can want opposite things — "cache this" from
   performance versus "don't cache authorization decisions" from security. That conflict is yours to settle
   or escalate; the Coder must never receive two findings that cancel each other.

### Disposition, as lead

Each of the three returns findings classed **Blocker / Should-fix / Nice-to-have**, each flagged
`behavior-preserving` or `needs-spec-change`.

| Finding                              | Action                                                                                       |
|--------------------------------------|----------------------------------------------------------------------------------------------|
| Blocker, behavior-preserving         | Goes on the consolidated list, which **you hold** — the Coder never sees it whole. Dispatch to the **Coder in `review-fix` mode**, **one finding per fresh spawn, sequentially**, each brief carrying that finding and the previous fix's SHA to merge: green baseline, apply in steps, suite after each, undo any red step rather than fixing forward. |
| Blocker, needs-spec-change           | **STOP and surface to the user.** A fix that changes observable behavior (a new 403, a redacted field, a rejected input, a paginated response) is a spec change — it belongs to the Specifier behind Gate 1, not to a silent patch. Never put one on the Coder's list; its own rules make it refuse. |
| Should-fix                           | On the list if behavior-preserving and cheap; otherwise carry into the cycle report with your recommendation. |
| Nice-to-have                         | Cycle report only.                                                                            |
| `codex_enabled: false` / Codex broke | Report **that reviewer** as **SKIPPED** in the cycle report, with the reason. Parallel spawning makes this cheap: one dead review never delays or cancels the other two. Never report an unrun review as passed. |

Four rules for running the loop:

- **You hold the consolidated list; the Coder receives one finding per fresh `review-fix` spawn.** Two
  findings in one brief is, by the Coder's own contract, a lead error. Dispatch sequentially — each spawn
  merges the previous fix's SHA, so every fix starts from a green, committed state — because batching the
  edits defeats the undo-on-red protocol: when the suite goes red you could no longer tell which change did
  it. And per-fresh-spawn keeps each fix in a small context instead of at the tail of a long one.
- **Re-run only the reviewers whose findings were acted on**, and re-run those in parallel too. A structural
  fix does not invalidate a security pass that found nothing.
- **The loop is bounded: three rounds, then the user.** One round = a batch of `review-fix` dispatches plus
  the re-run of the reviewers that raised them. Findings still arriving after round three go to the user with
  your recommendation instead of a fourth lap — three `xhigh` Codex runs per round is real cost, and a
  reviewer/fixer pair can oscillate. Every re-run brief also carries the already-dispositioned findings (one
  line each: finding → disposition) with the instruction to report only **new or changed** findings — a
  re-run reviewer re-reads the whole cycle diff and will otherwise re-raise what you already settled.
- **A "behavior-preserving" fix that required a test change is a contradiction.** The Coder is instructed to
  stop and report rather than edit a test to make its own change pass. If a report says a test changed, treat
  the finding as `needs-spec-change` and take it to the user.

### The needs-spec-change loop

A Blocker flagged `needs-spec-change` stops the autonomous run, but "surface to the user" starts a procedure —
it does not end the cycle:

1. Present the finding (the reviewer's wording, unfiltered) with your recommendation: amend the spec, or
   accept the risk.
2. **User accepts the risk** → record it in the ledger and the cycle report as user-accepted; the finding is
   closed and the pipeline continues.
3. **User wants the spec amended** → Gate 1 reopens, scoped to this change:
   - Spawn a **fresh `tran-forge-specifier`** with the finding and the affected feature file; it revises the
     Gherkin uncommitted and reports, exactly as in Phase 1.
   - Present the revised scenarios; loop on feedback; on approval the Specifier commits on base and reports
     the amended spec SHA. Record both spec SHAs in the ledger — the cycle's review diffs stay rooted at the
     original `SHA_spec` so the amendment itself is visible in them.
   - Spawn the Coder in **`implement`** mode with the amended spec SHA — not `review-fix`: the correction is
     spec-driven now, and the newly-red scenario drives it test-first.
   - **Re-run all three reviewers** on the Coder's new SHA. A spec change is a behavior change; the targeted
     re-run rule above covers behavior-preserving fixes and does not apply here.
4. Continue to Phase 6 with whatever SHA the reviews last signed off on.

Track the SHA. After the fix pass the current head moves; the Mutator merges whatever the reviews last signed
off on. Call it **`SHA_reviewed`** in your notes (it is `SHA_code` when no fix was needed).

## Phase 6 — Mutate (autonomous)

Spawn `tran-forge-mutator` with `SHA_reviewed` (and `SHA_spec` for the differential diff). It
returns **`SHA_final`**, the mutation score, survivor disposition, the per-scenario Gherkin-sensitivity sweep,
and the final verification table.

- Check its diff paths: the mutator's changes must touch **test code only** —
  `git diff <last-coder-sha>..SHA_final --name-only`, where `<last-coder-sha>` is the most recent Coder commit
  the Mutator merged (`SHA_reviewed`, or the latest escalation-fix SHA). Never root this diff at `SHA_spec`:
  that range includes the Coder's legitimate production work and would always flag. Production-path edits →
  reject the handoff and re-brief.
- Survivors needing production changes: spawn the **Coder in `review-fix` mode** (merge `SHA_final`, fix
  test-first, new SHA) → send the new SHA to the mutator to merge and re-verify. Bounded to ~2 iterations, as
  in the review phases. These fixes land **after** the review stage — one of the spine's two bounded
  exceptions. Default is to proceed (the fix is small, test-first, behavior-scoped), but if it touched a
  security-sensitive edge (authz, input handling, a query) or grew beyond a trivial diff, re-run the matching
  reviewer(s) on the new SHA before Phase 7 — and record either call in the ledger.
- **Gherkin-sensitivity sweep**: every scenario must be proven to fail when the rule it states is broken (the
  Mutator does this by breaking the behavior, running the acceptance suite, and reverting). `INSENSITIVE`
  scenarios are NOT auto-fixed — spec changes need the user — they go in the cycle report as decisions for the
  next cycle, and at cycle close (Phase 8 step 5) you offer to queue each one as a `Tighten scenario` entry in
  `requirements_file` so a later cycle actually picks the fix up.

## Phase 7 — Manual test (GATE 2)

Automated suites prove the code satisfies the spec. This phase asks the different question: does the thing
actually work when a person drives it?

1. Spawn `tran-forge-manual-tester` with `SHA_final`, `SHA_spec`, the approved feature file path(s), and the
   config's `Manual test` block. It merges into `tran-forge-verify` (fast-forward; commits nothing), drafts a
   numbered plan (Setup / Action / Expected) derived from the approved Gherkin **plus** the edges the Gherkin
   does not cover, executes it, and reports per-item ✅/❌/⚠.
2. Mode resolution (config `manual_test_mode`). Phase 7 **dispatches by surface**: each surface the diff touched
   gets the one mode that can actually see it. **Modes stack** — a full-stack change gets `browser+service`, and
   a change to code shared by a web shell and a native app gets `browser+mobile`:
   - `auto` (default) — resolve in this order, and combine rather than choose:
     1. the cycle's diff touched a path in `ui_src_paths` → **browser**
     2. the cycle's diff touched a path in `mobile_src_paths` → **mobile**
     3. the cycle's diff touched a REST endpoint or other externally reachable edge → **service**
     4. none of the above → **library**
   - `browser` — drive the rendered web UI through Playwright MCP at `ui_base_url`. Assertions come from the
     accessibility snapshot; screenshots are the human-facing evidence.
   - `mobile` — build the native app (`mobile_build`), install it on a simulator/emulator, and drive it with
     `mobile_driver` (`maestro` by default: a plain CLI, so no MCP dependency, and implicit waits mean markedly
     fewer FLAKY rows than `appium`). Assertions come from the view-hierarchy dump; screenshots are the
     human-facing evidence. A failed build or a stale binary is a BLOCKED finding, never a pass.
   - `service` — boot the app (`run_app`) and drive it over HTTP at `app_base_url`.
   - `library` — drive the public API directly through `library_repl` (`jshell` on a JVM repo, `npx tsx`/`node`
     on a TS one), a scratch harness, or the repo's CLI. Correct for katas and libraries with no HTTP surface.
   - `skip` — no manual phase; recorded as skipped in the cycle report.
3. **The surface guard — do not let a change pass on a surface nobody exercised.** For each surface the diff
   touched, a mode capable of *that* surface must have run:
   - `ui_src_paths` touched with no browser-capable mode (Playwright MCP not connected, `ui_base_url` unset, the
     UI won't start) → those items are `⚠ BLOCKED`, never `✅ PASS`. **`curl` against the endpoints behind a UI
     is not UI coverage.**
   - `mobile_src_paths` touched with no mobile-capable mode (`mobile_driver: none`, no device, build failed) →
     `⚠ BLOCKED`. **Browser device emulation is not native coverage, and neither is a passing web shell that
     happens to share source with the app.**
   Carry every BLOCKED item to the user at Gate 2 as an explicit gap. Shared source is not shared evidence.
4. **Present the manual-test report to the user verbatim** and ask for sign-off. This is Gate 2.
   - ❌ items → route to the **Coder in `review-fix` mode** (test-first: a failing manual case should become
     an automated test before it is fixed) → Mutator re-verifies → re-run the manual tester on the new SHA.
     This is the spine's other post-review exception — same rule as Phase 6: proceed by default, but when the
     fix touches a security-sensitive edge or outgrows a trivial diff, re-run the matching reviewer(s) on the
     new SHA first, and record the call in the ledger.
   - `⚠ FLAKY` items (browser scenario that failed once then passed) are **not** routed to the Coder — a
     browser-flake round trip costs a full re-verify loop. They go to the user in the report.
   - `⚠ BLOCKED` items are never treated as passes; they go to the user as a coverage gap.
   - Sign-off → proceed to cycle close.
   - The user may also sign off *with* known issues; record exactly what they accepted in the cycle report.

The manual tester never edits code and never commits — its only write surface is `target/` and its scratch dir
(screenshots, logs). Findings travel back through you.

## Phase 8 — Cycle close: merge back, artifact retention, report

In the main checkout on the base branch, as the lead:

1. Re-check the clean tree (`git status --porcelain`) — the one allowed entry is this cycle's in-progress
   ledger file under `<ledger_dir>`, which step 4 finalizes and commits.
2. Merge:
   `git merge --no-ff <SHA_final> -m "[KEY-123: ]tran-forge: <feature> (spec <SHA_spec>, code <SHA_code>, reviewed <SHA_reviewed>, mutate <SHA_final>)"`.
3. Run the config's `all_tests` on base — must be green. Red → investigate before reporting.
4. **Finalize and commit the cycle ledger** — the file you have been appending to since Gate 1 at
   `<ledger_dir>/<key-lowercase-or-slug>.md` (`ledger_dir` as resolved in Preflight 3, default `.tran-forge/`;
   if a phase skipped its entry, reconstruct it now from the role reports). Commit it on
   base (`[KEY-123: ]tran-forge: cycle ledger (<feature>)`). It exists because your context is not durable:
   scrollback dies with the session (or gets silently summarized long before that), and `/tran-forge-history`
   must reconstruct verdicts, incidents and your own calls from evidence — this file IS that evidence, and it
   is what makes "next feature in a fresh session" lossless. Record, tersely but **without truncating any
   table**:
   - feature, Jira key, per-role handoff SHAs (spec / code / reviewed / mutate), review round-trip count
   - per-phase verdict line (or SKIPPED + reason), test counts, coverage, mutation score
   - the consolidated findings table: finding, beat, severity, behavior flag, disposition
   - duplicates merged across the three reviews, and every contradiction you resolved — which way you called
     it, and why
   - incidents, and **your own wrong calls, uncensored** — a ledger that launders the lead is worth less than
     no ledger
   - both gate decisions, including anything the user accepted with known issues or ruled against your
     recommendation
5. **Artifact retention question.** List this cycle's requirement + spec + ledger artifacts and ask whether
   to keep them, defaulting to the config's `keep_requirements` / `keep_features` (the ledger defaults to
   keep):

   ```
   Artifacts this cycle:
     - requirements.txt entry "KEY-123 — <summary>"        [keep / drop]   (default: keep)
     - src/test/resources/features/key-123-<slug>.feature  [keep / drop]   (default: keep)
     - .tran-forge/key-123.md (cycle ledger)               [keep / drop]   (default: keep)
   Keep all?
   ```

   - **Keep** (the normal answer — the Gherkin is the living spec and the acceptance suite runs off it) →
     nothing to do; they are already committed.
   - **Drop** → remove them in a *separate follow-up commit on base after the merge*
     (`git rm <feature files>` / edit out the requirement entry, then commit
     `tran-forge: drop cycle artifacts (<feature>)`). Never rewrite the merge commit, and never drop a
     `.feature` file while a step definition or the acceptance runner still references it — if dropping would
     red the suite, say so and keep the file.
   - Dropping the Gherkin deletes the executable spec, and dropping the ledger deletes the only on-disk
     record `/tran-forge-history` can verify against — state the consequence in one line when the user
     chooses either. If they confirm, do it — it's their call.

   **INSENSITIVE scenarios become queued work here, or they die in the report.** For each one the sweep
   found, offer to append a `## Tighten scenario: "<name>"` entry (with the Mutator's why-it-is-insensitive
   line) to `requirements_file`, committed as a follow-up on base — so a later `/tran-forge` picks it up as
   an ordinary unimplemented requirement instead of the finding evaporating.
6. Present the **cycle report** to the user:
   - Feature + Jira key + scenario list
   - Per-role SHAs (spec / code / reviewed / mutate) and how many review round-trips the Coder took
   - Test counts, coverage, mutation score
   - Mutation blind spots covered this cycle (DB-integration tests for queries, controller + acceptance tests
     for endpoints), so the mutation score isn't read as proving what PIT can't see
   - **Design & architecture review**: Blockers fixed / open, Should-fix carried, how many of the Coder's own
     escalations it independently confirmed, or SKIPPED + reason
   - **Duplicate findings merged across the three parallel reviews**: <n> (and any contradiction you resolved
     between reviewers, with which way you called it)
   - **Security review**: same shape
   - **Performance review**: same shape
   - **Gherkin sensitivity**: SENSITIVE / INSENSITIVE per scenario — and, per INSENSITIVE one, whether the
     user queued a `Tighten scenario` entry in `requirements_file`
   - **Manual test**: mode(s), pass/fail counts, **UI coverage line** (browser-driven, n/a, or BLOCKED + why),
     any FLAKY items, what the user signed off (including anything accepted with known issues), or SKIPPED +
     reason
   - Documented equivalent mutants
   - Artifact retention decision
   - Open escalations (these are the user's decisions for next cycle)
7. If the config sets `jira_write_back: true`, *offer* to post the cycle report as a Jira comment and/or
   transition the ticket — and do it only on explicit confirmation, this cycle, for this ticket.
8. Ask: **next feature?**
   - Yes → **recommend a fresh context.** One full cycle deposits roughly half to all of
     `context_budget_tokens` here in reports, gates and routing; a second cycle stacked on top starts its own
     dedupe and needs-spec-change calls from degraded territory. The ledger, the merge commit and the worktrees carry
     everything the next cycle needs, so tell the user the recommended route is: end here, `/clear` (or a new
     session), then `/tran-forge <next>`. If they prefer to continue in-place, do so — but do not re-read
     this cycle's reports; the ledger is the record. Either way the team and worktrees are reused, and the
     next Specifier commit on base transitively syncs every role branch via the next handoff merges.
   - No → teardown.

## Teardown

- `SendMessage` `{type: "shutdown_request"}` to any live agents.
- If the manual tester booted the app, confirm the process is stopped and any seeded data cleaned up before
  teardown (its report states both).
- Ask the user whether to remove the worktrees (`git worktree remove .worktrees/<role>` ×6). Default: keep
  them for the next session. The `tran-forge-*` branches are kept as history either way.
- **Pushing anything is exclusively user-initiated, after this skill ends.** Never offer to push as part of
  the flow.

## Handoff protocol (condensed — full version in `constitution/workflow.md`)

- Handoff = commit pointer: 10-char SHA (`git rev-parse --short=10 HEAD`), commit message's last line
  `By <Role>.`.
- The receiving role's first working action is `git merge <sha>` into its own branch; conflict →
  `git merge --abort`, stop, report.
- The four read-only roles create no commits of their own: each moves **its own** `tran-forge-review-*` /
  `tran-forge-verify` branch with `git merge --ff-only <sha>` and reports the SHA it reviewed. One tree per
  role is what makes the three reviews safe to run concurrently. An `--ff-only` failure is an escalation, not
  something to work around.
- All SHAs, findings, and escalations route through you, the lead — roles never message each other.
- Specifier commits on base ⇒ base state flows transitively down the chain; no separate sync step.

## Error handling

- An agent reports "stopped: ambiguity/conflict" → resolve it yourself only if it is mechanical (e.g. relaying
  a missing path); otherwise surface it to the user. **Never instruct an agent to guess.**
- Preflight failures never auto-fix the user's repo (no stash, no reset, no checkout).
- An agent that died or hung → check `TaskList`, respawn with the same brief + the last known handoff SHA;
  the worktree and branch state survive respawns.
- A Codex run that times out or errors → one retry, then report **that one** phase SKIPPED with the error. The
  other two are running in parallel and are unaffected — a skipped review is never reported as a pass, and one
  dead review never cancels or delays the others.
- One reviewer hanging while the other two finish: don't dispatch fixes early to fill the time. Wait or kill
  it and record it SKIPPED — routing a fix while a reviewer is still reading the code invalidates its report.
- The Jira MCP failing is an input problem, not a pipeline problem: ask the user for the ticket text.
- The cycle aborts after Jira intake or Preflight 9 seeded an uncommitted requirements entry → say so and
  offer to commit or revert it before stopping; an entry left uncommitted fails the next run's clean-tree
  check.

## Resuming an interrupted cycle

A session can die mid-cycle. The repo state survives (branches, worktrees, the committed spec), and the
in-progress ledger holds the lead's state — so a fresh session re-enters instead of starting over.

Detect it at preflight: an uncommitted `<ledger_dir>/*.md`, or role branches ahead of base with no matching
cycle-close merge, means an interrupted cycle. Tell the user what you found and ask: resume, or abandon.

- **Resume** → read the ledger. Its last phase entry names the last completed phase and its handoff SHA;
  every role branch HEAD corroborates it (`git log -1 <branch>` — the `By <Role>.` line says who finished).
  Re-enter at the next phase with **fresh spawns** carrying the recorded SHAs — role contexts are disposable
  by design, and nothing needs the dead session's transcript. Anything mid-flight and unrecorded (a review
  that never reported, a fix dispatched but not committed) simply re-runs: that is the cheap, safe direction
  to err in.
- **Abandon** → never delete work silently. Show what each role branch holds beyond base and let the user
  decide what happens to it; at most, discard the uncommitted ledger on their explicit say-so.

Gate decisions are never assumed across the break: a Gherkin approval is proven by the spec commit on base;
anything after the ledger's last entry is treated as not having happened.

## Workflow reminders

- **The commit deviation is scoped**: roles commit only on their own `tran-forge-*` branches (Specifier: spec
  files only on base, post-approval; the four read-only roles commit nothing). Everything else about the house
  policy stands — especially **no pushes, ever, by any agent or by you**.
- Spawn sequentially, **except the three Codex reviews at Phases 3–5**, which go out in one message and run
  concurrently in their own worktrees. Never parallelize anything else — every other stage consumes the
  previous stage's commit.
- All git/mvn/codex calls use absolute paths with explicit `cd` (or Codex's `-C`).
- Persistence: between Gate 1 and Gate 2, keep going. The only valid stops are (a) the grilling (when it runs)
  and the Gherkin gate, (b) a Blocker finding that needs a spec change, (c) genuine ambiguity or an
  unresolvable red, (d) the manual-test sign-off, (e) the cycle report. Don't stop because a phase produced a
  long report — read it, decide, proceed.
- Before reporting the cycle done, re-walk Preflight → Jira intake (if run) → Grill (if run) → Specify → Code →
  Review ×3 (design/architecture, security, performance — all three actually returned, or are recorded
  SKIPPED) → Mutate → Manual test → Merge-back and verify each step actually completed with a green
  verification, or is explicitly recorded as skipped. Every accepted review finding must have a `review-fix`
  round-trip AND a re-run of the reviewer that raised it.

## Why no Refactorer — and what replaced it

A TDD pipeline conventionally puts a **Refactorer** between the Coder and the Mutator: a role that merges the
Coder's commit and improves the code without changing what it does. This flow deliberately has no such stage,
and that is its most consequential structural choice.

The reason is that a Refactorer without a review stage is the only thing standing between "code that works"
and "code that's decent," so it has to carry structural judgment on its own authority. This flow runs three
independent rival-model reviews instead, which is a strictly better source of the same judgment: a
dependency-rule violation identified by Codex against the project's own stated architecture rules is evidence,
where "the Refactorer felt this wanted extracting" is taste. Keeping both would leave one role restructuring
code on its own initiative *after* the point where anything reviews the result — the design that shipped would
not be the design that was graded.

The responsibilities such a role would own are distributed, not dropped:

| Refactorer owned                | Now owned by                                                          |
|---------------------------------|-----------------------------------------------------------------------|
| Local tidiness (names, duplication, dead code) | The **Coder**, as the third beat of its own inner loop — tidy the unit you just greened, while you still remember why you wrote it that way |
| Coverage bar + property tests   | The **Coder's** definition of done, with a mandatory red phase per gap-closing test (break the branch, prove the test fails, revert) — which is also why weak tests no longer reach the Mutator |
| Structural/architecture change  | The **design & architecture review** (Phase 3) finds it; the **Coder** applies it in `review-fix` mode |
| Behavior-preservation protocol  | Preserved exactly, as the Coder's `review-fix` mode: green baseline first, suite after every step, red steps undone rather than fixed forward, no test edited to make a "behavior-preserving" fix pass |

What this buys: every production write is reviewed (save the two bounded post-review exceptions at Phases 6–7,
which carry their own targeted re-review rule), one role writes production code, and two handoffs plus a
worktree disappear. What it costs: the Coder is now the single point of discipline for the whole pipeline —
so its rules are the ones not to weaken, and the `review-fix` protocol is not optional politeness. If you ever
add a Refactorer, put it **before** the reviews, never after, or the shipped design goes ungraded.
