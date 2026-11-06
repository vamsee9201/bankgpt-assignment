# What’s True Now

A snapshot-grounded knowledge system for the interface.ai Applied AI Engineer assessment. It answers from local website snapshots, preserves history, resolves source disagreements, and abstains when the evidence does not support an answer.

**Python 3.11+, standard library only. No API keys, paid models, live website requests, or external services.**

## Run

Keep the supplied participant kit outside this repository, or under the ignored `.local/` directory. Website snapshots and the assignment PDF are deliberately excluded.

```bash
python3 -m pip install -r requirements.txt
python3 cli.py --data /path/to/hackathon-knowledge-kit-participant.zip ask \
  "What's the APR for a 60-month auto loan on a 2025 vehicle?"

python3 cli.py --data /path/to/hackathon-knowledge-kit-participant.zip ask \
  "What is the 10-month jumbo certificate APY?" --as-of 2026-05-31

python3 cli.py --data /path/to/hackathon-knowledge-kit-participant.zip interactive
python3 cli.py --data /path/to/hackathon-knowledge-kit-participant.zip conflicts
```

The CLI also accepts an extracted kit directory, a `snapshots/` directory, or an individual snapshot ZIP. It reads ZIPs in memory and prints JSON, including source URLs, snapshot IDs, evidence quotes, confidence and resolution notes. Ingestion messages go to stderr, so JSON output can be redirected cleanly.

## Organizer contract

`solution.py` exposes `build()`. Its returned object implements:

```python
ks.ingest(snapshot)                      # Full website snapshot, oldest first
answer = ks.answer(question, as_of=None) # Answer with source evidence
conflicts = ks.conflicts()               # Qualified disagreements and resolutions
```

When loaded by the organizer harness, the implementation returns the harness’s exact `Answer`, `Source` and `Conflict` classes. Standalone callers receive compatible dataclasses. Importing or building the system does not read files or require a particular working directory.

## Evaluate

Extract the participant kit locally, then run its original scorer:

```bash
python3 scripts/evaluate.py --kit /path/to/hackathon-knowledge-kit-participant
```

Equivalently:

```bash
python3 /path/to/kit/harness/run_eval.py \
  --submission "$PWD" \
  --snapshots /path/to/kit/snapshots \
  --eval /path/to/kit/eval/public_eval.jsonl \
  --out .local/results
```

The public questions and scorer remain in the private participant kit. They are never imported by the solution. Evaluation outputs contain source excerpts, so keep them private as well. The wrapper defaults to ignored `.local/results`.

Run the independent, synthetic regression suite:

```bash
python3 -m unittest discover -s tests -v
```

See [SECURITY_REVIEW.md](SECURITY_REVIEW.md) for the prompt-injection audit and adversarial tests.

See [NOTES.md](NOTES.md) for architecture, source precedence, temporal semantics, tradeoffs, and evaluation caveats. See [VALIDATION.md](VALIDATION.md) for measured results.
