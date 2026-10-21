"""Release evaluation CLI; reports contain checks, never raw output/credentials."""

import argparse
import asyncio
from pathlib import Path

from .runner import evaluate, write_reports


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("deterministic", "live"), required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = asyncio.run(evaluate(args.mode))
        write_reports(report, args.report_dir)
    except (ValueError, OSError):
        print("Evaluation configuration/report unavailable; release blocked.")
        return 2
    print(
        f"AI evaluation: {'PASS' if report['passed'] else 'FAIL'} ({len(report['results'])} cases)"
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
