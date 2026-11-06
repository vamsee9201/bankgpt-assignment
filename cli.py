#!/usr/bin/env python3
"""Local demonstration: python cli.py --data participant.zip ask 'Question?'"""
import argparse
from dataclasses import asdict
import json
import sys
from knowledge.io import load_snapshots
from solution import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True, help='Private kit ZIP/folder or snapshots folder')
    sub = parser.add_subparsers(dest='command', required=True)
    ask = sub.add_parser('ask')
    ask.add_argument('question')
    ask.add_argument('--as-of')
    sub.add_parser('conflicts')
    sub.add_parser('interactive')
    args = parser.parse_args()
    ks = build()
    for s in load_snapshots(args.data):
        print(f'Ingesting {s.snapshot_id} ({len(s.pages)} pages)', file=sys.stderr)
        ks.ingest(s)
    if args.command == 'ask':
        print(json.dumps(asdict(ks.answer(args.question, args.as_of)), indent=2))
    elif args.command == 'conflicts':
        print(json.dumps([asdict(c) for c in ks.conflicts()], indent=2))
    else:
        print('Enter questions; Ctrl-D exits. Current = latest supplied snapshot.')
        while True:
            try:
                q = input('> ').strip()
            except EOFError:
                break
            if q:
                print(json.dumps(asdict(ks.answer(q)), indent=2))


if __name__ == '__main__':
    main()
