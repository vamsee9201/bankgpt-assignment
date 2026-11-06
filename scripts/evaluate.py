#!/usr/bin/env python3
"""Run the organizer's unchanged scorer against a private extracted participant kit."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kit', required=True, type=Path, help='Extracted participant kit directory')
    parser.add_argument('--out', type=Path, default=Path('.local/results'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    kit = args.kit.resolve()
    scorer = kit / 'harness/run_eval.py'
    if not scorer.is_file():
        parser.error(f'Organizer scorer not found: {scorer}')
    command = [sys.executable, str(scorer), '--submission', str(root),
               '--snapshots', str(kit / 'snapshots'), '--eval', str(kit / 'eval/public_eval.jsonl'),
               '--out', str(args.out.resolve())]
    raise SystemExit(subprocess.call(command, cwd=kit))


if __name__ == '__main__':
    main()
