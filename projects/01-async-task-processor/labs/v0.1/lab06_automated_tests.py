#!/usr/bin/env python3
"""Lab 06 — run the v0.1 unittest suite and exit nonzero if any test fails."""

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)


def main() -> int:
    print("Lab 06 — Automated tests")
    suite = unittest.defaultTestLoader.discover(str(PROJECT / "tests"))
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    passed = result.wasSuccessful()
    print(f"tests_run: {result.testsRun}")
    print(f"failures: {len(result.failures)}")
    print(f"errors: {len(result.errors)}")
    print(f"Result: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FAIL: {exc}")
        sys.exit(1)
