# Tran Forge Constitution — Workflow: Branches, Worktrees, Handoffs, Commits

Every Tran Forge role reads this file before doing any work. It defines the mechanics that make the pipeline
safe: isolated branches, commit-pointer handoffs, and lead-routed communication.

## Topology

- The target repo's **main checkout** holds the base branch (named in `tran-forge.config.md` → `base_branch`).
  The **Specifier works there directly** — specs land on base, and finished cycles merge back to base.
- Six git worktrees, created by the team lead during preflight (never by you). **Your spawn brief names your
  branch — use exactly that string**, `tran-forge-<role>`. Never "correct" a branch name, and never create a
  differently-prefixed branch yourself: the role's history lives on the branch you were given.


  | Role                 | Working directory       | Branch                   | Writes?   |
  |----------------------|-------------------------|--------------------------|-----------|
  | Specifier            | main checkout           | `<base_branch>`          | `.feature` files, post-approval |
  | Coder                | `.worktrees/coder`      | `tran-forge-coder`      | production + tests |
  | Architecture reviewer| `.worktrees/review-arch`| `tran-forge-review-arch`| **nothing** |
  | Security reviewer    | `.worktrees/review-security` | `tran-forge-review-security` | **nothing** |
  | Performance reviewer | `.worktrees/review-perf`| `tran-forge-review-perf`| **nothing** |
  | Manual tester        | `.worktrees/verify`     | `tran-forge-verify`     | **nothing** |
  | Mutator              | `.worktrees/mutator`    | `tran-forge-mutator`    | tests only |

- The four **read-only trees** (`review-arch`, `review-security`, `review-perf`, `verify`) belong to roles
  that commit nothing. Each moves its own branch to the SHA it was handed with
  **`git merge --ff-only <sha>`** and reads from there. `--ff-only` is a guarantee, not a convenience: a role
  that cannot fast-forward would have to create a merge commit, which it is forbidden to do. A failure there
  means something committed on that branch — stop and report it rather than working around it.

- **The three reviewers get one tree each because they run concurrently.** They are the only roles in this
  pipeline spawned together, and git cannot check the same branch out in two worktrees, nor can two agents
  safely share one index. Never work outside the tree named in your brief, and never reuse another role's
  scratch directory — while you run, two sibling reviewers are writing their own diffs.

- Your spawn brief gives you the absolute path of YOUR working directory. Your first action there is always:
  verify `git branch --show-current` matches your assigned branch, AND that `git status --porcelain` shows no
  uncommitted debris (build output the repo already ignores doesn't count; on the main checkout, the lead's
  in-progress cycle ledger under `ledger_dir` is expected and ignored). A wrong branch, a detached HEAD, or
  someone else's leftover changes → STOP and report — do not check out, clean, or repair anything.

## Your branch is your world

- You NEVER check out, commit to, reset, rebase, or otherwise touch any branch other than your own.
- The single exception: `git merge <handoff-sha>` of a commit that was explicitly handed to you, into your own
  branch.
- You never edit files under another role's `.worktrees/` directory.
- Every Bash call uses an absolute `cd` to your assigned working directory (the Bash tool's working directory
  persists between calls — never rely on it).

## Handoff = commit pointer (`merge_and_process`)

The unit of handoff between roles is a **commit, not a diff**:

1. When your role's work is done and verified, commit it on your own branch. The commit message's **last line
   is exactly `By <Role>.`** (e.g. `By Coder.`).
2. Obtain the 10-character SHA: `git rev-parse --short=10 HEAD`.
3. Report that SHA in your `TaskUpdate` completion comment. The team lead relays it to the next role.
4. When YOU receive a handoff SHA in your spawn brief or a lead message, your first working action is
   `git merge <sha>` into your own branch — then process it per your role.

Because the Specifier commits on the base branch and each role merges the previous role's commit, the base
branch's state flows transitively down the chain — there is never a separate "sync with base" step.

## Merge conflicts

On ANY conflict during a handoff merge:

```bash
git merge --abort
```

Then STOP and report the conflict (files, both sides' intent as far as you can tell) to the team lead via
`SendMessage`. Never resolve a conflict by guessing. The lead decides how to proceed.

## Commit policy — the sanctioned deviation

The house default for agent teams is "no commits without user confirmation." **Tran Forge deviates
deliberately**: commit-per-role-branch IS the handoff mechanism, so roles DO commit — but only inside these
bounds:

- Coder / Mutator: commits allowed **only on your own `tran-forge-*` branch** in your own
  worktree. Small commits during the work are encouraged; the final one carries the `By <Role>.` line.
- Specifier: commits **only spec (`.feature`) files, only on the base branch, and only after the team lead
  relays explicit user approval.** Until then everything stays uncommitted.
- **Architecture reviewer / security reviewer / performance reviewer / manual tester: no commits at all,
  ever.** They produce reports,
  not code. Their handoff is the SHA they *reviewed*, not a SHA they created. None of them has an `Edit`/`Write`
  tool, and any external tool they drive (e.g. `codex exec`) must be run with a read-only sandbox.
- The lead performs the cycle-close merge into base, and any follow-up artifact-retention commit the user asks
  for at cycle close. No role ever merges into base.

## Forbidden operations — always, for every role

- `git push` (any form, any remote). Pushing is exclusively a user decision after the cycle ends.
- `git push --force`, `git rebase`, `git commit --amend` on any commit that has been handed off.
- Checking out or committing to any branch that is not yours.
- `git stash` on someone else's tree; deleting branches or worktrees.
- Editing `.feature` files unless you are the Specifier.

## Communication — everything routes through the team lead

- You never `SendMessage` another role directly. Findings, escalations, questions, and handoff SHAs go to the
  **team lead** via your `TaskUpdate` completion comment or `SendMessage`.
- Your `TaskUpdate` completion comment IS your report — follow the report template in your role file.
- After completing a task, stand by. The lead decides what happens next.
