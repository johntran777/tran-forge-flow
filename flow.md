# Tran Forge Flow

Build a software development lifecycle flow called **Tran Forge**, which consists of:

1. An orchestrator
2. A list of agents

## Task

Read the description below and study the reference implementation, then mimic and understand
the flow to build the orchestrator and the list of agents.

- **Reference repo:** [unclebob/swarm-forge](https://github.com/unclebob/swarm-forge)

## Description

Tran Forge is an AI agent coordinator system designed for automated, Test-Driven Development
(TDD). It uses tmux, shell scripts, and Git worktrees to orchestrate specialized AI agents that
independently plan, implement, and refactor code on isolated branches before merging changes.

## Workflow

The system workflow consists of a rigid, automated pipeline:

1. **Specifier** — Converts informal plain-text requirements into formal Gherkin specifications.
2. **Coder** — Executes a TDD loop, writing production code only to make the generated Gherkin
   tests pass.
3. **Refactorer** — Modifies and cleans the code to enforce software craftsmanship boundaries
   (e.g., Clean Architecture, SOLID principles).
4. **Mutator** — Performs mutation testing to purposefully introduce small bugs, verifying that
   the tests properly catch errors.

## Output

The result of the flow creation should be stored under the folder `tran-forge-flow`.

## Additional features for the flow
+At the beginning of the flow, the orchestrator can optionally take in a Jira ticket
+Asking for keeping the requirement, Gherkin test cases files.
+Add a code review step for performance, code review for security (OWASP top 10) using Codex right after the Refactorer step
+Split the Clean Architecture review out of the Refactorer into its own step, "design and architecture review",
 and make the security and performance reviews two separate steps as well — three separate code reviews, each
 driven through Codex.
+Drop the Refactorer stage. The shape wanted is: Coder -> the three code reviews -> any finding goes straight
 back to the Coder. Local tidiness moves into the Coder's own TDD loop; cross-cutting restructuring arrives as
 a review finding instead of an agent's unreviewed judgement.
+Add a manual testing step after the Mutator step
+Should we add cucumber for the mutator testing?


