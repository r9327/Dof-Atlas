from __future__ import annotations

import argparse
import random
import sys
import unittest
from collections import defaultdict
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]


def flatten(suite: unittest.TestSuite) -> list[unittest.TestCase]:
    tests: list[unittest.TestCase] = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            tests.extend(flatten(item))
        else:
            tests.append(item)
    return tests


def reproducible_suite(tests: Iterable[unittest.TestCase], seed: int) -> unittest.TestSuite:
    groups: dict[str, list[unittest.TestCase]] = defaultdict(list)
    for test in tests:
        identifier = test.id()
        owner = identifier.rsplit(".", 1)[0]
        groups[owner].append(test)
    rng = random.Random(seed)
    owners = sorted(groups)
    rng.shuffle(owners)
    ordered: list[unittest.TestCase] = []
    for owner in owners:
        methods = sorted(groups[owner], key=lambda test: test.id())
        rng.shuffle(methods)
        ordered.extend(methods)
    return unittest.TestSuite(ordered)


def load_tests(loader: unittest.TestLoader, root: Path, modules: list[str], pattern: str) -> list[unittest.TestCase]:
    if modules:
        return flatten(loader.loadTestsFromNames(modules))
    return flatten(loader.discover(str(root / "tests"), pattern=pattern, top_level_dir=str(root)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run unittest contracts in a reproducible pseudo-random order.")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--pattern", default="test_*.py")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--modules", nargs="*")
    parser.add_argument("--list", action="store_true", help="Print order without executing tests.")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    loader = unittest.TestLoader()
    tests = load_tests(loader, root, args.modules or [], args.pattern)
    suite = reproducible_suite(tests, args.seed)
    print(f"ATLAS_RANDOM_SEED={args.seed}")
    if args.list:
        for test in flatten(suite):
            print(test.id())
        return 0
    result = unittest.TextTestRunner(verbosity=1 if args.quiet else 2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
