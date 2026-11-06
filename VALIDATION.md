# Validation

The implementation is evaluated with the organizer’s unchanged `harness/run_eval.py` and all five supplied snapshots. Website files and per-answer outputs remain private under `.local/`.

Post-security-review public run on CPython 3.11.13:

| Measure | Result |
| --- | ---: |
| Questions | 40 |
| Weighted question accuracy | 0.9411 |
| Public aggregate (conflict gold unavailable) | 0.9411 |
| Stale-value trap hits | 0 |
| Exceptions/timeouts | 0 |
| Paraphrase consistency | 1.0000 |
| Repeat consistency | 1.0000 |
| p95 answer latency | 0.16 seconds |
| Ingestion | 18.5 seconds |

These are public-development results, not an estimate of hidden-set performance. The public run does not measure conflict precision/recall because the conflict gold is withheld. The audit is inspected separately and source/qualifier policies are tested on synthetic cases. Timing depends on interpreter and hardware.

The independent suite currently contains 39 synthetic regression tests (30 functional and nine adversarial source-security tests). It covers historical cutoffs, out-of-order and repeated ingestion, deleted pages, date parsing, spell-out paraphrases, balance and model-year qualifiers, metric separation, explicit expirations, conflicting authoritative sources, source quotation, numeric formatting, fee conditions, related-article leakage, and abstention for absent products.

Reproduce with the commands in README.md. See NOTES.md for the two public-label/scorer limitations and the source-credit limitation intentionally preserved.
