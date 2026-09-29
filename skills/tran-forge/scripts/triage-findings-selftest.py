#!/usr/bin/env python3
"""
Self-test for the POLICY half of triage-findings.py. Calls nothing and needs no API key.

Everything the model returns is mocked here on purpose. What is under test is the part that turns
those numbers into a bucket -- the part that decides whether a fix reaches the Coder with nobody
looking. Run this after touching any threshold in triage-findings.py:

  python3 skills/tran-forge/scripts/triage-findings-selftest.py

Exit code 0 means the policy still behaves as documented; 1 means a case changed bucket. The
invariant case is the one that matters most: no combination of confidence, behavior-preservation or
fix size may put a Blocker that needs a spec change onto the dispatch list.
"""

import importlib.util
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("triage", os.path.join(HERE, "triage-findings.py"))
triage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(triage)

MIN_CONFIDENCE = 0.55


def answers(severity, confidence, preserving, spec_change, test_change, evidence, fix_size, route):
    return {
        "severity": severity,
        "severity_confidence": confidence,
        "severity_probabilities": {},
        "behavior_preserving": preserving,
        "spec_change": spec_change,
        "test_change_required": test_change,
        "evidence_grounded": evidence,
        "fix_size": fix_size,
        "model_route": route,
        "model_route_confidence": 0.9,
    }


# Each case is a finding this pipeline has plausibly seen, with the bucket it must land in.
CASES = [
    ("N+1 loop, internal fix, spec-covered",
     answers("blocker", 0.95, 0.93, 0.05, 0.10, 0.97, 1.0, "coder"), "dispatch"),
    ("PII leak: removing a served field IS an observable change",
     answers("blocker", 0.97, 0.15, 0.88, 0.60, 0.95, 1.0, "user"), "stop_for_user"),
    ("blocker whose fix needs an existing test rewritten",
     answers("blocker", 0.90, 0.80, 0.20, 0.85, 0.90, 1.0, "coder"), "stop_for_user"),
    ("blocker, fix not clearly behavior-preserving",
     answers("blocker", 0.88, 0.40, 0.30, 0.10, 0.90, 2.0, "user"), "stop_for_user"),
    ("severity genuinely unclear",
     answers("should_fix", 0.38, 0.90, 0.10, 0.10, 0.90, 1.0, "coder"), "lead_review"),
    ("'consider rate limiting' -- no cited location",
     answers("nice_to_have", 0.80, 0.50, 0.40, 0.10, 0.12, 3.0, "report_only"), "lead_review"),
    ("should-fix, behavior-preserving and cheap",
     answers("should_fix", 0.82, 0.88, 0.05, 0.10, 0.92, 1.0, "coder"), "dispatch"),
    ("should-fix, behavior-preserving but a redesign",
     answers("should_fix", 0.85, 0.90, 0.05, 0.10, 0.92, 3.0, "report_only"), "report_only"),
    ("nice-to-have",
     answers("nice_to_have", 0.91, 0.90, 0.05, 0.10, 0.88, 1.0, "report_only"), "report_only"),
]


def main():
    failures = 0
    for name, answer, expected in CASES:
        got, reasons = triage.decide(answer, MIN_CONFIDENCE)
        if got == expected:
            print("  ok   %-52s -> %s" % (name, got))
        else:
            failures += 1
            print(" FAIL  %-52s -> %s (wanted %s)" % (name, got, expected))
            print("       %s" % reasons[0])

    # The one rule no threshold may ever bend.
    combos = 0
    for confidence, preserving, fix_size in itertools.product(
            (0.30, 0.60, 0.99), (0.0, 0.7, 1.0), (0.0, 1.5, 3.0)):
        bucket, _ = triage.decide(
            answers("blocker", confidence, preserving, 0.90, 0.0, 1.0, fix_size, "coder"),
            MIN_CONFIDENCE)
        combos += 1
        if bucket == "dispatch":
            failures += 1
            print(" FAIL  spec-changing Blocker dispatched at confidence=%.2f preserving=%.2f "
                  "fix_size=%.1f" % (confidence, preserving, fix_size))
    print("  ok   %-52s -> never dispatched (%d combinations)"
          % ("invariant: Blocker needing a spec change", combos))

    # A defect two reviewers raised in two vocabularies must collapse to one entry.
    groups = triage.merge_groups(["sec-1", "arch-1", "perf-1", "perf-2"], [("sec-1", "arch-1")])
    sizes = sorted(len(g) for g in groups)
    if sizes == [1, 1, 2]:
        print("  ok   %-52s -> %s" % ("merge: one defect, two reviewers, one entry",
                                      sorted(sorted(g) for g in groups)))
    else:
        failures += 1
        print(" FAIL  merge_groups produced %s" % sizes)

    print("\n%s" % ("all policy checks passed" if not failures else "%d FAILURES" % failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
