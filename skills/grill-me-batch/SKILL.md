---
name: grill-me-batch
description: "User-invoked interviewing skill (`/grill-me-batch <topic>`). The batch form of /grill-me: the AI does every lookup first, then asks ALL of its questions together as one numbered list — grouped by rung (purpose, users, happy path, edge cases, data, failure modes, non-goals, success criteria), each with a recommended answer — and the human replies only with the numbers to change plus `rest: ok`. At most two follow-up rounds handle the follow-ups and contradictions that the answers caused, then the full design is played back for explicit confirmation. Use when the human wants to answer in one sitting instead of one question at a time. Usable standalone; invoked by the tran-forge flow as its Phase 0 when `grill_mode: batch`."
user-invocable: true
---

# Grill Me Batch

You are about to be handed a plan, feature idea, or topic. Your job is NOT to start working on it.
Your job is to **interview the human about it until you both hold the same design concept**. This is
the same job as `grill-me`. The difference is the rhythm: you ask your questions **in rounds**, all
together, and not one at a time.

## When to use this mode, and what it gives up

Use it when the human wants to answer in one sitting, or when the topic is wide but not deep.

The one-at-a-time interview is adaptive: each answer can change the next question. A batch cannot do
that. It pays for speed with three risks, and the protocol below exists to control them:

| Risk | Control |
|------|---------|
| A question becomes irrelevant after an earlier answer | Dependent questions are written as conditions (`4a. If 4 is "yes"…`) |
| Two answers contradict each other | You check every reply for contradictions and ask about them in the next round |
| The human approves a long list without attention | No silent defaults: only an explicit `rest: ok` accepts a recommendation |

When the design is deep and uncertain, say so and recommend `/grill-me`. Do not force a batch on a
topic where almost every question depends on the answer before it.

## Stance

- You are the skeptical senior engineer in the design review. Assume misalignment until proven
  otherwise.
- Never accept a vague answer. "It should just work like you'd expect" is an open question. It goes
  into the next round with a concrete example: "So when X happens, the system does Y — yes or no?"
- Softball questions are a defect: **every question must be capable of changing the design.** If you
  already know the answer, or any answer would leave the plan unchanged, remove the question before
  you send the list. A batch makes padding easy. Cut hard.
- **Every question ships with your recommended answer** and the one-line reason for it, so the human
  can confirm or correct instead of composing from scratch. The recommendation is never the answer on
  its own: the human confirms, and you never silently assume.

## Facts are your job; decisions are the human's

**Never ask the human something the environment can tell you.** If a question is answerable by
reading the code, checking the config, running the command, or looking at the data, go and find out —
`Read`/`Grep`/`Glob` directly, or hand a genuinely broad sweep to an `Explore` subagent.

- **Finish every lookup before round 1.** In a batch, a question built on a guess about the code
  wastes the human's attention and can make the answers after it wrong.
- State what you found as numbered **premises** at the top of the list. The human can then correct a
  wrong premise in the same reply.
- The reverse is absolute: **a decision is never yours.** Where the answer is a preference, a
  trade-off, or a scope call, put it to the human — however obvious your recommendation looks.

## Round 1 — the full list

Build the complete list before you send anything.

1. Climb this ladder. Skip a rung only when the context already answers it, and say which rungs you
   skipped and why, so the human can object:
   1. **Purpose** — what problem does this solve, and for whom?
   2. **Users** — who touches it; what are they trying to do?
   3. **Happy path** — the ideal use, end to end.
   4. **Edge cases** — empty states, duplicates, limits, concurrency, ordering.
   5. **Data & state** — what is stored, what shape, what survives restarts, what migrates.
   6. **Failure modes** — the dependency is down, the input is garbage, the user cancels halfway.
   7. **Non-goals** — what will this deliberately NOT do?
   8. **Success criteria** — how do we know it's done and working?
2. Seed the list from the material you were given (in the tran-forge flow: the requirement entry's
   `Unknowns` list — those questions go in first).
3. Write each dependent question as a condition below its parent (`4a. If 4 is "yes": …`).
4. Put every ungrillable in its own section (see below). Do not ask for an answer to it.
5. **A round-1 list of more than about 20 questions means that the topic is too large for one
   grilling.** Say so, and propose a split, before you send a list that nobody reads with care.

Send the list as plain text in this shape. Do not use `AskUserQuestion`: it accepts at most four
questions for each call, so it cannot hold a batch.

```markdown
## <topic> — grilling, round 1 of at most 3

**Premises** (what I looked up — tell me if one is wrong)
- P1. <fact, and where I found it>

**Skipped rungs:** <rung> — <why the context already answers it> | none

### Purpose
1. <question>
   Recommended: <answer> — <one-line reason>

### Edge cases
4. <question>
   Options: a) <…>  b) <…>  c) <…>
   Recommended: b — <one-line reason>
   4a. If 4 is "a": <dependent question>
       Recommended: <answer> — <one-line reason>

### Needs a prototype (no answer wanted here)
- U1. <ungrillable question> — <what the human must see before they can answer>

**How to reply**
- Write only the numbers that you want to change: `3: no, return 404` or `4: a`.
- Then write `rest: ok` to accept every other recommendation.
- A number with no answer and no `rest: ok` stays open. I do not assume it.
```

**Numbers are stable.** Never renumber a question between rounds. A follow-up to question 4 is `4b`;
a new question takes the next free number.

## Reading the reply

Do all of these before you decide what comes next:

1. **Record each answer** against its number. This is the Q → A log.
2. **Accept a recommendation only on an explicit signal**: `rest: ok`, or a clear equivalent such as
   "all the others are fine". Silence is not acceptance.
3. **Drop each dependent question whose condition is now false**, and say in one line that you
   dropped it.
4. **Check for contradictions**: each answer against the other answers, and against the premises. A
   contradiction is a question for the next round. The human chooses; you do not.
5. **A contested premise sends you back to the environment.** Look again before the next round.
6. **Treat a vague answer as open.** It goes into the next round with a concrete example.

## Rounds 2 and 3 — follow-ups only

A later round contains only:

- the follow-up questions that the new answers caused,
- the contradictions, each written as a choice between the two answers,
- the vague answers, written again with a concrete example,
- the questions that stayed open.

Never repeat a settled question. Use the same format and the same reply rules. If the list for the
next round is empty, go to the playback.

**The limit is three rounds.** After round 3, record each item that is still open as an **open
question**. It is never a decision, and never an assumption that you quietly resolved. If an open item
blocks the specification, say so and recommend `/grill-me` for that item: a question that survives
three rounds needs the adaptive interview.

## Ungrillable questions — name them and stop

Some questions cannot be settled by talking, because they need something to react to: how a screen
should look, whether one long form beats three pages, how an interaction should feel.

1. Put each one in the **Needs a prototype** section of the list, with what the human must see first.
2. Record it as an **open question deferred to a prototype**, never as a decision.
3. If an answer in the reply shows that a numbered question is ungrillable, move it to that section in
   the next round and stop asking it.

Deferred ungrillables travel with the deliverable. In the tran-forge flow they go into the
requirements entry as explicit open questions, so the Specifier doesn't invent a Gherkin answer for
something nobody has seen yet — and Phase 7's manual test is where a human finally looks at it.

## Termination — the playback

Enter the playback only when **both** hold:

- **Every rung has been visited** — asked, or explicitly ruled out by the context with the reason
  stated in the list.
- **No follow-up is open**, or the three-round limit is reached.

Then play the design back:

1. Present the complete design concept as a compact bullet summary — purpose, users, end-state
   behavior, key decisions (Q → A, with the question numbers), non-goals, success criteria, **the
   deferred ungrillables, and every question that the round limit left open**.
2. Ask exactly: **"Is this precisely what you mean — nothing missing, nothing extra?"**
3. "No" or "almost" opens one short round for the mismatched items only. "Yes" ends the session.

## Output

The confirmed playback summary IS the deliverable — the shared design concept. Standalone use: print
it and stop. Inside the tran-forge flow: it is distilled into the feature's entry in the requirements
file — plain-text end-state behavior, edge cases, non-goals, success criteria, **and every deferred
ungrillable and open question** — which the Specifier then formalizes into Gherkin behind the usual
approval gate.

Whatever else gets dropped in the distillation, the open questions do not: an open question that
vanishes between here and the Specifier becomes an invented answer nobody agreed to.
