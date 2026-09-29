#!/usr/bin/env python3
"""
Triage and dedupe the three reviewers' findings with TypeSafe, so the lead dispatches a ranked,
merged, contradiction-free list instead of re-reading three reports in prose.

Phases 3-5 return findings from three reviewers running blind to each other. SKILL.md then asks the
lead to dedupe across the reports, class each finding, flag behavior-preserving vs needs-spec-change,
resolve contradictions and rank the result. Every one of those is a small typed judgment. This makes
them with TypeSafe's System One API and keeps the POLICY here in code, where you can read it, diff it
and change a threshold without re-running inference.

What the model decides, and what this file decides, are deliberately separate:

  model  ->  severity, behavior-preserving, spec-change, test-change, evidence, fix size, sameness
  code   ->  a Blocker that needs a spec change STOPS for the user and never reaches the Coder;
             low confidence goes to the lead; contradictory pairs are pulled from dispatch;
             duplicates merge into one entry naming both reviewers; the dispatch list is ranked.

Two passes, both parallel:

  1. One request per finding, carrying every question at once (speculative fan-out). Questions are
     evaluated in parallel against one shared state, so asking seven costs seven questions' tokens
     and roughly one question's latency.
  2. One request per CROSS-REVIEWER pair, asking sameness and contradiction together. Pairs within a
     single reviewer's own report are skipped: a reviewer does not duplicate itself, and the
     quadratic term is what makes this pass expensive.

Usage
-----
  triage-findings.py --findings findings.json [--out triage.json] [--model jev-latest]
                     [--min-confidence 0.55] [--dry-run] [--workers 8]

  --findings        input JSON, shape below
  --out             write the full triage JSON here (default: stdout after the summary)
  --min-confidence  severity confidence below this routes the finding to the lead, never the Coder
  --dry-run         build and print the requests, call nothing; works with no API key
  --workers         parallel in-flight requests (default 8)

Needs TYPESAFE_API_KEY in the environment. Nothing is installed: this speaks the HTTP API directly
with the standard library, like every other script in this repo.

Input shape
-----------
  {
    "cycle": "PROJ-1234",
    "approved_gherkin": "Feature: ...",            # the text behind Gate 1; spec-change is judged against it
    "project_blocker_rule": "no N+1; ...",         # the config's own Blocker definition, verbatim
    "changed_files": ["src/main/java/..."],
    "findings": [
      {"id": "sec-1", "reviewer": "security", "title": "...", "detail": "...",
       "location": "src/main/java/Foo.java:42", "claimed_severity": "Blocker"}
    ]
  }

`reviewer` should be one of architecture / security / performance. `claimed_severity` is the
reviewer's own grade and is passed through as evidence, not believed: a reviewer grades against its
own lens, and the whole point of this pass is a consistent grade across all three.

Exit codes: 0 triage complete; 2 nothing to triage (no findings); 3 input unusable; 4 every request
failed. A non-zero exit means: fall back to the manual consolidation in SKILL.md. Do not act on a
partial list without saying it is partial.
"""

import argparse
import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"
ENV_KEY = "TYPESAFE_API_KEY"

# Retry only what the API documents as retryable. A 422 is a bug in this file, not a blip.
RETRY_STATUSES = {429, 529}
MAX_ATTEMPTS = 5

# --- policy thresholds -------------------------------------------------------------------------
# Tuned conservatively on purpose: every threshold here decides whether a fix is applied without a
# human looking at it. Raise them after you have watched a few cycles, not before. The asymmetry is
# deliberate -- it is cheap to send the lead something it could have decided, and expensive to send
# the Coder a fix that changes behavior behind the user's back.
SPEC_CHANGE_STOP = 0.50     # at or above this, the fix alters promised behavior -> the user decides
PRESERVING_FLOOR = 0.65     # below this, do not hand it to the Coder's behavior-preserving protocol
TEST_CHANGE_FLAG = 0.50     # at or above this, the "fix" needs a test edited -> a contradiction
EVIDENCE_FLOOR = 0.40       # below this, the finding is a general worry with no cited location
CONTRADICTION_FLAG = 0.50   # at or above this, two findings pull in opposite directions
SAME_DEFECT_MERGE = 0.50    # choice probability at or above this merges two findings into one entry
CHEAP_FIX_MAX = 1.5         # a should-fix is dispatched only if its fix_size score is at most this


# --- questions ---------------------------------------------------------------------------------
# Every question below is one judgment a reviewer's colleague makes in a second given the finding and
# the approved spec. Nothing here asks the model to plan, weigh or decide the outcome.

def finding_questions():
    return {
        "severity": {
            "type": "choice",
            "instructions": (
                "Grade the defect described in `finding.detail` against this codebase's own "
                "definition of a Blocker in `project_blocker_rule`. Judge the defect itself, not "
                "how strongly the reviewer in `finding.reviewer` worded it."
            ),
            "criteria": {
                "blocker": (
                    "Ships a real defect: data loss or corruption, a security hole, a wrong result, "
                    "a failure under ordinary load, or anything `project_blocker_rule` names."
                ),
                "should_fix": (
                    "A genuine problem that does not by itself block the merge. It makes the code "
                    "harder to change, slower than it should be, or risky under conditions the "
                    "change does not yet meet."
                ),
                "nice_to_have": (
                    "A preference, a style point, or a speculative concern about code paths this "
                    "change does not create."
                ),
            },
        },
        "behavior_preserving": {
            "type": "noul",
            "instructions": (
                "Can the defect in `finding.detail` be fixed without changing any behavior that a "
                "caller outside the changed code can observe?"
            ),
            "criteria": {
                "true": (
                    "The fix is internal: structure, naming, an added index, a query rewritten to "
                    "return the same rows, a resource closed. Same inputs still give same outputs."
                ),
                "false": (
                    "The fix changes what a caller sees: a new rejection or status code, a field "
                    "removed or redacted, a response paginated, an input newly refused."
                ),
            },
        },
        "spec_change": {
            "type": "noul",
            "instructions": (
                "Would fixing `finding.detail` require behavior that `approved_gherkin` never "
                "promises? Judge the fix against the scenarios actually written there, not against "
                "what the feature arguably ought to do."
            ),
            "criteria": {
                "true": (
                    "The fix adds, removes or alters an observable outcome no scenario in "
                    "`approved_gherkin` states. The specification would have to be amended first."
                ),
                "false": (
                    "The fix is fully covered by the scenarios already in `approved_gherkin`, or it "
                    "changes nothing a scenario can observe."
                ),
            },
        },
        "test_change_required": {
            "type": "noul",
            "instructions": (
                "Would fixing `finding.detail` force an EXISTING test to be edited, rather than a "
                "new test to be added alongside the ones already passing?"
            ),
            "criteria": {
                "true": "An existing test asserts the behavior the fix changes, so it must be rewritten.",
                "false": "The fix leaves existing tests passing unchanged; any new coverage is additive.",
            },
        },
        "evidence_grounded": {
            "type": "noul",
            "instructions": (
                "Does `finding.detail` point at a specific place in this change -- a named file, "
                "symbol, query or line that appears in `changed_files` -- rather than raising a "
                "general concern about this kind of code?"
            ),
            "criteria": {
                "true": "It cites concrete code in this change and says what is wrong with it.",
                "false": "It is a category of risk, a reminder, or a concern with no cited location.",
            },
        },
        "fix_size": {
            "type": "score",
            "instructions": "How much code has to move to fix the defect in `finding.detail`?",
            "criteria": [
                "One line or one expression, in one place.",
                "One method or one class, with no change to any signature other callers use.",
                "Several files, or a signature other code calls.",
                "A redesign: a new collaborator, an inverted dependency, or a changed data model.",
            ],
        },
        # Advisory only. This is the holistic question the composed rules replace, kept as a
        # cross-check: code NEVER acts on it. Where it disagrees with the composed route, the entry
        # is flagged so the lead looks -- a disagreement usually means the finding reads two ways.
        "route": {
            "type": "choice",
            "instructions": (
                "Who should handle `finding.detail` next in a pipeline where the Coder makes only "
                "behavior-preserving fixes, the Specifier owns the approved specification, and the "
                "user decides anything that changes promised behavior?"
            ),
            "criteria": {
                "coder": "A behavior-preserving fix the Coder can apply under the approved spec.",
                "specifier": "The specification itself is wrong or silent and must be amended first.",
                "user": "A judgment call about risk or scope that only the person owning the work can make.",
                "report_only": "Worth recording in the cycle report; not worth a fix in this cycle.",
            },
        },
    }


def pair_questions():
    return {
        "relation": {
            "type": "choice",
            "instructions": (
                "Two reviewers read the same change without seeing each other's report. Do "
                "`finding_a` and `finding_b` describe the same underlying defect in the code?"
            ),
            "criteria": {
                "same_defect": (
                    "The same line or mechanism is wrong in both, described in two vocabularies. "
                    "One fix in one place closes both."
                ),
                "related": (
                    "Different defects with a shared cause or neighbourhood. One fix would probably "
                    "touch the other, but neither closes the other."
                ),
                "distinct": "Separate defects. Fixing one leaves the other exactly as it was.",
            },
        },
        "contradictory": {
            "type": "noul",
            "instructions": (
                "Do `finding_a` and `finding_b` ask for opposite changes to the same code, so that "
                "applying both is impossible or undoes one of them?"
            ),
            "criteria": {
                "true": (
                    "The two fixes pull against each other -- cache this versus never cache this, "
                    "batch these versus isolate these, widen this versus narrow this."
                ),
                "false": "Both fixes can be applied to the same code without either weakening the other.",
            },
        },
    }


# --- transport ---------------------------------------------------------------------------------

def call(state, questions, model, api_key, timeout=60):
    """One POST to the evaluation endpoint, with backoff on the statuses the API says to retry."""
    body = json.dumps({"state": state, "model": model, "questions": questions}).encode()
    last = None
    for attempt in range(MAX_ATTEMPTS):
        req = urllib.request.Request(
            API_URL,
            data=body,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as err:
            last = "HTTP %d: %s" % (err.code, err.read().decode(errors="replace")[:400])
            if err.code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS - 1:
                raise RuntimeError(last) from err
            # Honor the server's own pacing when it sends one; otherwise back off exponentially.
            retry_after = err.headers.get("retry-after") if err.headers else None
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2.0 ** attempt
            time.sleep(delay)
        except urllib.error.URLError as err:
            last = "connection: %s" % err
            if attempt == MAX_ATTEMPTS - 1:
                raise RuntimeError(last) from err
            time.sleep(2.0 ** attempt)
    raise RuntimeError(last or "unreachable")


def run_parallel(jobs, workers):
    """jobs: list of (key, callable). Returns {key: result} and {key: error string}."""
    out, errs = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn): key for key, fn in jobs}
        for future in concurrent.futures.as_completed(futures):
            key = futures[future]
            try:
                out[key] = future.result()
            except Exception as err:  # noqa: BLE001 - one dead request must not kill the pass
                errs[key] = str(err)
    return out, errs


# --- composition -------------------------------------------------------------------------------

def read_answers(response):
    """Flatten one response into the plain numbers the policy below reads."""
    ans = response.get("answers", {})
    sev = ans.get("severity", {})
    route = ans.get("route", {})
    fix = ans.get("fix_size", {})
    return {
        "severity": sev.get("choice"),
        "severity_confidence": sev.get("confidence", 0.0),
        "severity_probabilities": sev.get("probabilities", {}),
        "behavior_preserving": ans.get("behavior_preserving", {}).get("noul", 0.0),
        "spec_change": ans.get("spec_change", {}).get("noul", 0.0),
        "test_change_required": ans.get("test_change_required", {}).get("noul", 0.0),
        "evidence_grounded": ans.get("evidence_grounded", {}).get("noul", 0.0),
        "fix_size": fix.get("score", 0.0),
        "model_route": route.get("choice"),
        "model_route_confidence": route.get("confidence", 0.0),
    }


def decide(a, min_confidence):
    """The whole policy, in one readable place. Returns (bucket, reasons).

    Order matters: the hard stops come first, so no later rule can talk a Blocker that needs a spec
    change onto the Coder's list.
    """
    reasons = []

    if a["severity"] == "blocker" and a["spec_change"] >= SPEC_CHANGE_STOP:
        reasons.append(
            "Blocker whose fix changes behavior the approved Gherkin never promised "
            "(spec_change=%.2f). SKILL.md: this stops for the user; it is the Specifier's, "
            "not a silent patch." % a["spec_change"]
        )
        return "stop_for_user", reasons

    if a["test_change_required"] >= TEST_CHANGE_FLAG and a["behavior_preserving"] >= PRESERVING_FLOOR:
        reasons.append(
            "Reads as behavior-preserving (%.2f) but looks like it needs an existing test edited "
            "(%.2f). SKILL.md calls that a contradiction -- treat it as needs-spec-change."
            % (a["behavior_preserving"], a["test_change_required"])
        )
        return "stop_for_user", reasons

    if a["severity_confidence"] < min_confidence:
        reasons.append(
            "Severity confidence %.2f is below the %.2f floor: the grade is not clear enough to act "
            "on unreviewed." % (a["severity_confidence"], min_confidence)
        )
        return "lead_review", reasons

    if a["evidence_grounded"] < EVIDENCE_FLOOR:
        reasons.append(
            "Cites no specific location in the change (evidence=%.2f): a general concern, not a "
            "finding the Coder can act on." % a["evidence_grounded"]
        )
        return "lead_review", reasons

    if a["severity"] == "blocker":
        if a["behavior_preserving"] >= PRESERVING_FLOOR:
            reasons.append(
                "Blocker, behavior-preserving (%.2f), covered by the approved spec (spec_change="
                "%.2f)." % (a["behavior_preserving"], a["spec_change"])
            )
            return "dispatch", reasons
        reasons.append(
            "Blocker, but the fix is not clearly behavior-preserving (%.2f). Below the %.2f floor "
            "the Coder's protocol does not apply." % (a["behavior_preserving"], PRESERVING_FLOOR)
        )
        return "stop_for_user", reasons

    if a["severity"] == "should_fix":
        if a["behavior_preserving"] >= PRESERVING_FLOOR and a["fix_size"] <= CHEAP_FIX_MAX:
            reasons.append(
                "Should-fix, behavior-preserving (%.2f) and cheap (fix_size=%.2f): SKILL.md puts "
                "this on the list." % (a["behavior_preserving"], a["fix_size"])
            )
            return "dispatch", reasons
        reasons.append(
            "Should-fix, but not both behavior-preserving (%.2f) and cheap (fix_size=%.2f): carry "
            "it into the cycle report with a recommendation."
            % (a["behavior_preserving"], a["fix_size"])
        )
        return "report_only", reasons

    reasons.append("Nice-to-have: cycle report only.")
    return "report_only", reasons


def merge_groups(finding_ids, same_pairs):
    """Union-find over the same_defect pairs, so a defect all three reviewers raised becomes one entry."""
    parent = {fid: fid for fid in finding_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in same_pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    groups = {}
    for fid in finding_ids:
        groups.setdefault(find(fid), []).append(fid)
    return list(groups.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--findings", required=True)
    parser.add_argument("--out")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--min-confidence", type=float, default=0.55)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        with open(args.findings) as handle:
            doc = json.load(handle)
    except (OSError, ValueError) as err:
        print("cannot read --findings: %s" % err, file=sys.stderr)
        return 3

    findings = doc.get("findings") or []
    if not findings:
        print("no findings to triage", file=sys.stderr)
        return 2
    for f in findings:
        if not f.get("id") or not f.get("reviewer"):
            print("every finding needs an id and a reviewer: %r" % f, file=sys.stderr)
            return 3

    shared = {
        "approved_gherkin": doc.get("approved_gherkin", ""),
        "project_blocker_rule": doc.get("project_blocker_rule", ""),
        "changed_files": doc.get("changed_files", []),
    }

    # Cross-reviewer pairs only. A reviewer does not duplicate itself, and this term is quadratic.
    pairs = [
        (findings[i], findings[j])
        for i in range(len(findings))
        for j in range(i + 1, len(findings))
        if findings[i]["reviewer"] != findings[j]["reviewer"]
    ]

    if args.dry_run:
        print(json.dumps({
            "would_send": {"finding_requests": len(findings), "pair_requests": len(pairs)},
            "example_finding_request": {
                "state": dict(shared, finding=findings[0]),
                "model": args.model,
                "questions": finding_questions(),
            },
            "example_pair_request": ({
                "state": {"finding_a": pairs[0][0], "finding_b": pairs[0][1],
                          "changed_files": shared["changed_files"]},
                "model": args.model,
                "questions": pair_questions(),
            } if pairs else None),
        }, indent=2))
        return 0

    api_key = os.environ.get(ENV_KEY)
    if not api_key:
        print("%s is not set" % ENV_KEY, file=sys.stderr)
        return 3

    fq, pq = finding_questions(), pair_questions()

    jobs = [
        (f["id"], (lambda f=f: call(dict(shared, finding=f), fq, args.model, api_key)))
        for f in findings
    ]
    responses, errors = run_parallel(jobs, args.workers)
    if not responses:
        print("every finding request failed; first error: %s" % next(iter(errors.values()), "?"),
              file=sys.stderr)
        return 4

    pair_jobs = [
        ((a["id"], b["id"]), (lambda a=a, b=b: call(
            {"finding_a": a, "finding_b": b, "changed_files": shared["changed_files"]},
            pq, args.model, api_key)))
        for a, b in pairs
        if a["id"] in responses and b["id"] in responses
    ]
    pair_responses, pair_errors = run_parallel(pair_jobs, args.workers)

    by_id = {f["id"]: f for f in findings}
    answers = {fid: read_answers(resp) for fid, resp in responses.items()}

    same_pairs, contradictions = [], []
    for (a_id, b_id), resp in pair_responses.items():
        rel = resp.get("answers", {}).get("relation", {})
        contra = resp.get("answers", {}).get("contradictory", {}).get("noul", 0.0)
        probs = rel.get("probabilities", {})
        if probs.get("same_defect", 0.0) >= SAME_DEFECT_MERGE:
            same_pairs.append((a_id, b_id))
        if contra >= CONTRADICTION_FLAG:
            contradictions.append({
                "a": a_id, "b": b_id, "contradictory": round(contra, 3),
                "note": "Resolve or escalate before dispatching; the Coder must never receive two "
                        "findings that cancel each other.",
            })

    contradicted = {fid for c in contradictions for fid in (c["a"], c["b"])}

    entries = []
    for members in merge_groups(list(answers), same_pairs):
        # The group speaks with its most serious member's voice: the highest blocker probability.
        lead_id = max(members, key=lambda m: answers[m]["severity_probabilities"].get("blocker", 0.0))
        a = answers[lead_id]
        bucket, reasons = decide(a, args.min_confidence)

        computed_route = {"dispatch": "coder", "stop_for_user": "user",
                          "lead_review": "user", "report_only": "report_only"}[bucket]
        disagrees = a["model_route"] is not None and a["model_route"] != computed_route

        clashing = [m for m in members if m in contradicted]
        if clashing:
            bucket = "lead_review"
            reasons.append("Contradicts another reviewer's finding (%s); pulled from dispatch."
                           % ", ".join(sorted(clashing)))

        entries.append({
            "finding_ids": sorted(members),
            "reviewers": sorted({by_id[m]["reviewer"] for m in members}),
            "title": by_id[lead_id].get("title", ""),
            "merged_from": len(members),
            "bucket": bucket,
            "severity": a["severity"],
            "signals": {k: (round(v, 3) if isinstance(v, float) else v)
                        for k, v in a.items() if k != "severity_probabilities"},
            "reasons": reasons,
            "model_route_disagrees": disagrees,
        })

    rank = {"blocker": 0, "should_fix": 1, "nice_to_have": 2}
    entries.sort(key=lambda e: (rank.get(e["severity"], 3),
                                -e["signals"]["severity_confidence"]))

    result = {
        "cycle": doc.get("cycle"),
        "model": next(iter(responses.values())).get("model"),
        "counts": {
            "findings_in": len(findings),
            "entries_out": len(entries),
            "merged_away": len(findings) - len(entries),
            "failed_findings": len(errors),
            "failed_pairs": len(pair_errors),
        },
        "usage": {
            "requests": len(responses) + len(pair_responses),
            "input_tokens": sum(r.get("usage", {}).get("input_tokens", 0)
                                for r in list(responses.values()) + list(pair_responses.values())),
        },
        "dispatch": [e for e in entries if e["bucket"] == "dispatch"],
        "stop_for_user": [e for e in entries if e["bucket"] == "stop_for_user"],
        "lead_review": [e for e in entries if e["bucket"] == "lead_review"],
        "report_only": [e for e in entries if e["bucket"] == "report_only"],
        "contradictions": contradictions,
        "errors": {"findings": errors, "pairs": pair_errors},
    }

    payload = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w") as handle:
            handle.write(payload + "\n")

    c = result["counts"]
    print("triaged %d findings -> %d entries (%d merged) | dispatch %d | stop-for-user %d | "
          "lead %d | report %d | contradictions %d"
          % (c["findings_in"], c["entries_out"], c["merged_away"], len(result["dispatch"]),
             len(result["stop_for_user"]), len(result["lead_review"]),
             len(result["report_only"]), len(contradictions)), file=sys.stderr)
    if errors or pair_errors:
        print("PARTIAL: %d finding and %d pair requests failed -- say so before acting on this list"
              % (len(errors), len(pair_errors)), file=sys.stderr)
    if not args.out:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
