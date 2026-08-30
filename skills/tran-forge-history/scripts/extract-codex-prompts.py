#!/usr/bin/env python3
"""
Recover the verbatim prompts sent to Codex during a Tran Forge cycle's code reviews.

Codex logs every session to ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl, including the full
prompt text. This matches sessions to reviewers by the session's recorded `cwd` (each reviewer
runs `codex exec -C <its own worktree>`), and writes one .txt per run.

Usage
-----
  extract-codex-prompts.py --repo /path/to/repo --out /path/to/outdir [--date 2026-08-07]

  --repo   the target repo; its .worktrees/review-* dirs identify the reviewers
  --out    directory to write <beat>-<n>.txt into
  --date   restrict to one YYYY-MM-DD of logs (default: search all dates)
  --sessions  override the sessions root (default ~/.codex/sessions)

Two traps this handles, both of which silently produce wrong output if ignored:

  1. The first large user turn in a session is Codex's own `<recommended_plugins>` environment
     preamble, NOT the prompt. Turns containing that marker are skipped.
  2. A cycle usually has TWO runs per beat (first pass + re-review). Both are kept, numbered by
     timestamp order, because the re-review prompt is scoped differently and is worth showing.

Exit codes: 0 wrote at least one prompt; 2 found sessions but no usable prompt; 3 found no
sessions at all. A non-zero exit means: say so in the document. Do not reconstruct the prompt.
"""

import argparse
import glob
import json
import os
import re
import sys

PREAMBLE_MARKER = "recommended_plugins"
# a real review prompt is thousands of chars; this guards against matching a stray short turn
MIN_PROMPT_CHARS = 600

BEATS = {
    "review-arch": "arch",
    "review-security": "sec",
    "review-perf": "perf",
}


def turn_text(payload):
    """Flatten a rollout turn's content to text, whatever shape it is stored in."""
    c = payload.get("content")
    if isinstance(c, list):
        return "".join(p.get("text", "") for p in c if isinstance(p, dict))
    return c if isinstance(c, str) else ""


def session_cwd(path):
    """The working directory the session ran in — how we identify the reviewer."""
    with open(path, errors="replace") as fh:
        for line in fh:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            for cand in (o.get("payload") or {}, o):
                cwd = cand.get("cwd")
                if isinstance(cwd, str) and cwd:
                    return cwd
    return None


def best_prompt(path):
    """The longest user turn that looks like a review brief, excluding Codex's own preamble."""
    best = ""
    with open(path, errors="replace") as fh:
        for line in fh:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            p = o.get("payload", o)
            if p.get("role") != "user":
                continue
            t = turn_text(p)
            if not t or PREAMBLE_MARKER in t:
                continue
            if len(t) > len(best):
                best = t
    return best.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", help="YYYY-MM-DD")
    ap.add_argument("--sessions", default=os.path.expanduser("~/.codex/sessions"))
    a = ap.parse_args()

    if not os.path.isdir(a.sessions):
        print(f"no Codex sessions root at {a.sessions} — report the prompts as unrecoverable",
              file=sys.stderr)
        return 3

    if a.date:
        y, m, d = a.date.split("-")
        pattern = os.path.join(a.sessions, y, m, d, "rollout-*.jsonl")
    else:
        pattern = os.path.join(a.sessions, "*", "*", "*", "rollout-*.jsonl")

    files = sorted(glob.glob(pattern))
    if not files:
        print(f"no rollout logs matched {pattern}", file=sys.stderr)
        return 3

    repo = os.path.realpath(a.repo)
    os.makedirs(a.out, exist_ok=True)

    # collect (beat, timestamp, path) for sessions whose cwd is one of this repo's review worktrees
    found = []
    for f in files:
        cwd = session_cwd(f)
        if not cwd:
            continue
        try:
            real = os.path.realpath(cwd)
        except OSError:
            continue
        if not real.startswith(repo):
            continue
        for wt, beat in BEATS.items():
            if real.rstrip("/").endswith(wt):
                ts = re.search(r"rollout-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})", os.path.basename(f))
                found.append((beat, ts.group(1) if ts else "", f))
                break

    if not found:
        print("found rollout logs but none ran in this repo's review worktrees", file=sys.stderr)
        return 2

    wrote = 0
    per_beat = {}
    for beat, ts, f in sorted(found, key=lambda x: (x[0], x[1])):
        prompt = best_prompt(f)
        if len(prompt) < MIN_PROMPT_CHARS:
            print(f"  SKIP {beat} {ts}: no turn over {MIN_PROMPT_CHARS} chars "
                  f"(got {len(prompt)}) — likely not a review run", file=sys.stderr)
            continue
        per_beat[beat] = per_beat.get(beat, 0) + 1
        name = f"{beat}-{per_beat[beat]}.txt"
        with open(os.path.join(a.out, name), "w", encoding="utf-8") as out:
            out.write(prompt)
        label = "pass 1" if per_beat[beat] == 1 else f"re-review {per_beat[beat] - 1}"
        print(f"  {name:12s} {len(prompt):6d} chars  {ts}  ({label})")
        wrote += 1

    if not wrote:
        print("no usable prompts recovered — report them as unrecoverable in the document",
              file=sys.stderr)
        return 2

    print(f"\nwrote {wrote} prompt(s) to {a.out}")
    print("Sanity-check the char counts before embedding: a real review prompt is thousands of "
          "characters. Escape with html.escape() before putting them in <pre>.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
