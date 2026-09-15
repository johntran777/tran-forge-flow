---
name: tran-forge-history
description: "User-invoked documentation skill (`/tran-forge-history [KEY-123]`). Reconstructs a completed (or in-flight) Tran Forge cycle from the evidence it left behind — the base branch's commit ledger, the role branches, the Gherkin artifacts, surefire and PIT reports, the requirements file's decision entries, and the real Codex review prompts recovered from `~/.codex/sessions` rollout logs — and renders it as a single self-contained local HTML page with an interactive pipeline diagram: click any stage for its full record, step with arrow keys, overlay the incidents, filter the findings. Writes a standalone document (`<!doctype html>` + `<meta charset=\"utf-8\">`), never an artifact fragment. Fabricates nothing: an unrecoverable number is reported as unrecoverable."
user-invocable: true
---

# Tran Forge History

You are producing the **record** of a Tran Forge cycle: what the pipeline did to one ticket, in enough
detail that someone who wasn't there can audit it — and someone who was there can find the SHA, the
finding, or the decision they half-remember.

The deliverable is one **local, self-contained HTML file** with an interactive pipeline diagram.

## Two failure modes to design against

Everything below exists to avoid these:

1. **A trophy cabinet.** A record that lists only successes is not a record. The failures — crashed
   agents, blocked runs, wrong calls by the lead — are the most useful content in the document,
   because they are what a reader can learn from and what a sceptic will look for first. Include them
   with the same prominence as the metrics.
2. **Confident invention.** Every number, SHA, verdict and prompt must come from evidence on disk. If
   something cannot be recovered, the document says so in the document. A plausible reconstruction
   presented as fact poisons the whole artifact, because the reader cannot tell which parts to trust.

## Inputs

Invoked as `/tran-forge-history`, optionally with a ticket key and/or a target repo path.

- **Target repo**: the path argument if given, else `$CLAUDE_PROJECT_DIR`.
- **Ticket**: an argument matching `[A-Z][A-Z0-9]+-\d+`. If absent, find it: the most recent
  `<KEY>: tran-forge:` merge commit on the base branch, else the ticket prefix dominating recent
  commits, else ask.
- **Cycle boundary**: the commit *before* the cycle's first commit (usually the scaffolding commit
  `<KEY> tran-forge scaffolding:`) through the merge commit. Everything measured from that base —
  call it `SHA_pre` — so "what did this effort change" has one unambiguous answer.

Works on an in-flight cycle too. Mark unreached phases `pending` rather than inventing them.

## Phase 1 — Gather evidence, verify nothing on trust

Read the repo's config (`tran-forge.config.md`) first: it names the base
branch, the requirements file, the features dir, the thresholds and the commands. Then collect:

```bash
cd <repo>
git log --format='%h|%s' <SHA_pre>..HEAD              # the ledger, in order
git diff --diff-filter=A --name-only <SHA_pre>..HEAD  # new files
git diff --diff-filter=M --name-only <SHA_pre>..HEAD  # touched files
git diff --shortstat <SHA_pre>..HEAD                  # totals
git worktree list                                     # role branches + heads
git log -1 --format='%s' HEAD                         # merge msg carries all four handoff SHAs
```

The merge commit message is the spine: a Tran Forge merge records `spec`, `code`, `reviewed` and
`mutate` SHAs. Take the chain from there rather than guessing which commit was which handoff.

Then, per artifact class:

- **Gherkin** — count scenarios per file (`grep -cE '^\s*Scenario' <features_dir>/*.feature`) and sum.
  Report the per-file breakdown; it is what makes the total auditable.
- **Decisions** — the requirements file's numbered decisions and `R*` refinement entries, each with
  the commit that recorded it. These are the human rulings; they are the most valuable content after
  the failures, because they explain *why* the code looks the way it does.
- **Mutation** — parse `<module>/target/pit-reports/mutations.xml`. **PIT writes
  `status='KILLED'` with single quotes**, so match `status='[A-Z_]+'` and `status="[A-Z_]+"` both, or
  you will silently compute 0%. Report total / killed / survived and the per-class breakdown.
  Then recover **how the Mutator worked**, not only the score: the PIT invocation (differential pass
  over the cycle's classes, then the full run — `mutation_report` and the target classes from the
  config and the Mutator's report), the disposition of every survivor (test strengthened / equivalent
  mutant documented / escalated to the Coder), and the **Gherkin sensitivity sweep** — per scenario,
  the surgical break applied and the SENSITIVE / INSENSITIVE verdict. The sweep is the only mutation
  test the specification gets, so a record that shows the score and omits the sweep undersells the
  stage.
- **Manual test** — the mode(s) resolved for the cycle (`browser` / `mobile` / `service` / `library` /
  `skip`, stacked when the diff spanned surfaces), the driver behind each (Playwright MCP, Maestro or
  Detox or Appium, HTTP client, `library_repl` or the repo's CLI), the base URL or device target, the
  plan's pass / fail / FLAKY / BLOCKED counts, the **UI coverage line**, the screenshot evidence
  referenced per UI scenario, and whether the tester confirmed the app process, browser and seeded
  data were cleaned up. Source: the ledger's Phase 7 entry first, else the tester's report as relayed.
  Nothing in `target/` records this, so when neither exists the document must say the mode and driver
  are unrecovered — not default to "manual test passed".
- **Tests** — prefer the figure printed by the run itself. **`surefire-reports/*.xml` accumulates
  across runs**: classes deleted or added between runs leave stale XML, so an aggregate over that
  directory can disagree with the run's own output. When two sources disagree and you cannot
  reconcile them, publish the one you can defend and **say in the document that the other disagreed**
  rather than picking the nicer number.
- **Verdicts** — the reviewers' and Mutator's reports as relayed in the cycle. Where a claim was
  verified on disk during the cycle, say it was verified; where it was taken from a report, attribute
  it to the report.
- **Cycle ledger** — newer cycles write one at cycle close: `<ledger_dir>/<key-lowercase-or-slug>.md`
  (the config's `ledger_dir`, default `.tran-forge/`), committed on base. When it exists, **prefer it**
  as the on-disk source for verdicts, finding dispositions, the dedupe and contradiction calls,
  incidents, the lead's own errors, and both gate decisions — it is the lead's contemporaneous record,
  and it satisfies "verify on disk" where scrollback cannot. **Absent → fall back to the bullets above
  exactly as written**; cycles that predate the ledger have none, and that is not a gap worth flagging.
  When the ledger and another source disagree, that is a finding about the evidence, as ever: publish
  the defensible one and name the disagreement.

## Phase 2 — Recover the real Codex prompts

The three code reviews are driven through the Codex CLI, and **Codex logs every session**, including
the full prompt. Recover the actual text; do not paraphrase from the reviewers' summaries.

Logs live at `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`. Match a session to a reviewer **by its
recorded `cwd`**, which is that reviewer's worktree (`.worktrees/review-arch` etc.). Two traps:

- The first large user turn is Codex's own `<recommended_plugins>` environment preamble, not the
  prompt. Skip any turn containing `recommended_plugins`.
- Both the first pass and the re-review appear, distinguished by timestamp. Keep both — the
  re-review prompts are shorter and scoped to the fix-pass diff, which is itself worth showing.

`scripts/extract-codex-prompts.py` in this skill does the matching and writes one `.txt` per run.
Run it, then verify the character counts are plausible (a real review prompt is thousands of
characters; a few hundred means you matched the wrong turn).

If the logs are gone or the reviews were skipped, **say so in the document** and fall back to the
invocation plus the reviewers' own description of what they fed in. Never present a reconstruction as
the prompt.

Reading the prompts back is usually the most interesting part of the whole exercise: most of a good
review prompt is *constraint* — telling the model what it does not own, and which of the codebase's
apparent violations are house convention. Draw that out in the prose rather than just dumping text.

## Phase 3 — Build the document

Load **`artifact-design`** to calibrate treatment, then **`artifact-diagramming`** for the figure.
Follow both. The subject's own world supplies the palette and type: this is a pipeline of commit
pointers, branches, SHAs and verdicts, so monospace-forward typography is grounded rather than
decorative, and semantic verdict colours (pass / caution / fail / accepted-risk) must stay separate
from the accent hue.

### It is a standalone document, not an artifact fragment

**The single most common bug in this skill's output.** Write a complete document:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KEY-123 — Tran Forge cycle record</title>
<style>…</style>
</head>
<body>
… content …
<script>…</script>
</body>
</html>
```

Omitting `<meta charset="utf-8">` makes the browser guess an encoding, and every em dash, arrow,
middle dot and check mark in the document turns to mojibake. An artifact fragment gets a `<head>`
supplied at publish time; a local file does not. Verify afterwards with
`iconv -f UTF-8 -t UTF-8 <file>` and by checking the charset line is present.

No external requests: no font CDNs, no script CDNs, no remote images. It must open from disk, offline.

### The diagram must show the mechanism

A box per phase in a straight line is the prose restated. Draw the three things a reader cannot get
from a list:

- **Handoffs are commit pointers routed through the lead.** Put a lead rail above the spine with both
  human gates on it and dashed drops to the stages they block. That makes "roles never talk to each
  other, the lead is a real chokepoint" visible instead of asserted.
- **The fix loop.** A distinct (dashed, semantic-coloured) arrow from consolidation back to the Coder,
  labelled with how many findings travelled it. This is the pipeline's thesis — one role writes
  production code, every finding returns to it — and a left-to-right sequence hides it completely.
- **The parallel review fan-out.** Three boxes off one commit, converging on a consolidation node,
  each labelled with its own read-only worktree. The isolation is *why* concurrency is safe, so label
  it.

Mark the two human gates in a semantic colour distinct from the accent — they are the only points
where a person decides, and they should be findable at a glance.

Hand-author inline SVG with native shapes, `viewBox` sized to content, `currentColor` for structure so
both themes work, arrowheads as `<marker>` or `<polygon>`. Keep text 11–13px **at rendered scale** —
if the viewBox is much wider than the display width, text shrinks below legibility, so either size the
viewBox near the display width or put the figure in an `overflow-x:auto` container with a `min-width`.
Wrap it in `<figure>` with a `<figcaption>` stating the claim, plus `role="img"` and an `aria-label`
carrying the same claim. No `<script>` or `<style>` inside the SVG — page-level JS driving it is fine.

### Interactivity that earns its place

- **Clickable stages** → a detail panel with role, worktree and branch, handoff SHA in and out, a
  verdict pill, a **tooling line**, detailed prose, and that stage's incidents. This is the core;
  everything else is secondary. The tooling line names what the stage ran and how: for a review, the
  Codex model, effort and sandbox flag; for the Mutator, the PIT invocation and the sweep's
  scenario count; for the manual tester, each mode with its driver and target. A stage whose tooling
  is unrecovered says so on that line.
- **Arrow-key stepping** through stages in pipeline order, with focus moved so keyboard users get the
  same affordance.
- **Incident overlay toggle** — markers on the stages that actually went wrong. Off by default; the
  reader opts in.
- **Findings filter** by beat and disposition, with a live count.
- **Theme toggle** on top of `prefers-color-scheme`, tokenised so `data-theme` wins in both
  directions.

Every node needs `tabindex="0"`, `role="button"`, an `aria-label`, and Enter/Space handling. Respect
`prefers-reduced-motion`.

### Sections

1. **Header** — ticket, one-line description of what shipped, verdict pills (including the honest
   ones: *ticket not closed*, *nothing pushed*, *N accepted risks*), and a KPI strip.
2. **The pipeline** — the figure, the overlay toggle, the detail panel.
3. **Commit ledger** — every commit in order, handoff SHAs marked, gates marked.
4. **Decisions** — the numbered decisions and `R*` refinements, each with its recording commit.
   **Flag the ones that went against the lead's recommendation**; that asymmetry is real information
   about how the cycle was steered.
5. **Review findings** — filterable: finding, severity, behavior-preserving vs needs-spec-change,
   beat, disposition. State the dedupe and any contradiction the lead resolved, with which way it was
   called.
6. **The prompts sent to Codex** — collapsible blocks, each with the exact `codex exec` invocation
   above the verbatim prompt, HTML-escaped. Say plainly that these are recovered from the rollout
   logs, and include a note on **what Codex got wrong** — the findings its human driver dropped,
   downgraded or re-classified. A prompts section that implies the output was authoritative is
   misleading.
7. **Where it went wrong** — every incident, and separately **the lead's own errors**, each with what
   it cost. Do not soften these.
8. **Verification stack** — one row per verification stage (unit suite, acceptance suite, each Codex
   review, PIT, Gherkin sensitivity sweep, each manual-test mode) with the tool, the invocation or
   driver, the target it ran against, and the result it produced — so a reader can see not just
   *that* the code was checked but *with what and how*. Then the blind spots the tooling structurally
   cannot see and how they were covered instead (DB-integration tests for new queries, controller and
   acceptance tests for new endpoints, any cross-module limits of the mutation tool, and — for the
   manual test — every surface the diff touched that no mode could exercise, with the BLOCKED reason).
9. **Still open** — anything blocking, delivery state (pushed? PR? CI? ticket status?), accepted risks
   with a "do not silently fix" warning, unfiled follow-ups, and anything never manually exercised.

## Hard rules

- **Never fabricate.** No invented SHA, count, verdict, or prompt. Unrecoverable → say so, in the
  document, where the number would have been.
- **Verify on disk.** Agent reports in these cycles have been wrong. Where you can check a claim with
  `git`, `grep` or a report file, check it, and prefer the checked value.
- **Reconcile or disclose.** Two sources disagreeing is a finding about the evidence, not a licence to
  choose. Publish the defensible one and name the disagreement.
- **Include the lead's errors.** If the cycle record shows the orchestrator was wrong about something
  — a mis-read metric, a bad assumption that cost a run — it goes in. A record that launders the
  orchestrator's mistakes is worth less than no record.
- **Attribute Codex explicitly** on every review stage: which model, which effort, `--sandbox
  read-only`, and that a different model family grading the work is the point.
- **Attribute the Mutator and the manual tester the same way.** PIT invocation, survivor
  dispositions and the sensitivity sweep for the Mutator; mode, driver, target, counts and UI coverage
  line for the manual tester. A verdict pill with no tooling behind it is an assertion, not a record.
- **Local file, complete document, UTF-8 declared.** See above.
- **Write nothing into the repo's tracked state.** The document is a new untracked file. Say where it
  is, and offer: leave untracked, add one line to `.git/info/exclude` (never the user's `.gitignore`),
  or commit it. Let the user choose.
- **Read-only on the cycle's artifacts.** Never amend, rewrite or tidy the commits you are
  documenting; never touch a `.feature` file or the requirements file.

## Output

Default location: the target repo root, `<key-lowercase>-tran-forge.html` (e.g.
`proj-1234-tran-forge.html`). If the user names a path, use it. Report the absolute path and the
`open` command.

Then validate before reporting done, and show the results:

```bash
iconv -f UTF-8 -t UTF-8 <file> >/dev/null && echo "valid UTF-8"
grep -c 'meta charset="utf-8"' <file>
grep -cE 'src="http|href="http|@import' <file>     # must be 0
# tag balance: html/head/body/style/script/svg/details/pre
```

Finally, offer to publish it as a shareable Artifact — but only offer. It is a local document by
default because that is what this skill is for; publishing is the user's call.
