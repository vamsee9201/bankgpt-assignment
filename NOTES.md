# Design notes

## Approach

The system is deterministic and entirely local. Ingestion extracts typed observations from Markdown rate tables, fee schedules and a few tightly scoped narrative formats. A financial observation retains its domain, product, term/balance/model-year qualifiers, metric, value, URL, snapshot ID and supporting row. APR, APY and dividend rate are different metrics. Jumbo, standard, business, personal, purchase, refinance and retirement products retain their identities. Minimum opening/earning conditions accompany table answers. Numeric and Markdown formatting differences are normalized for comparison.

For unstructured content, the system builds an inverted lexical index with inverse-document-frequency weighting. Headings, product names, authority and passage length influence ranking. Related-article recommendations and image content are excluded. Domain-specific evidence selection covers membership, branch announcements, contact channels and other recurring website structures. It is intentionally a bounded extraction/retrieval system, not a general language-model assistant: it cannot reason freely over arbitrary prose or promise complete fact extraction.

All answer values are extracted during `ingest()`. There is no question-to-answer lookup, embedded copy of website facts, model call, or import of the evaluation set. Public questions informed the supported question intents; regression tests use independently constructed, synthetic credit-union data with different values.

## What “current” means

Each ingestion supplies a **full** snapshot, not a delta. Every dated view owns its own page map, facts and search index. Answering without `as_of` uses the newest ingested date. Explicit ISO dates select the latest snapshot on or before that day, never a future snapshot. Dates before the first observation abstain. An explicit argument takes precedence over a date extracted from the question. Supported embedded forms include `as of YYYY-MM-DD` and `as of Month YYYY`; month-only references use month end. Arbitrary relative dates are not inferred from the wall clock.

Pages omitted from a later full snapshot do not remain available as current knowledge. Historical answers still retain them. Snapshot dates determine observation availability; article publication dates rank dated news statements but do not replace observation dates. A still-visible old announcement is historical evidence, not proof that a promotion is still running. Explicit ISO offer expirations in narrative certificate facts exclude expired offers. Implicit or complex promotional validity language is a limitation.

## Resolving disagreement

Dedicated product rate tables outrank generic/legacy pages, marketing, old news and calculator examples. Within the selected product domain, the highest source authority is selected before matching terms: otherwise a stale page’s old model-year label can accidentally appear to describe a different valid product. This deliberately favors precision, at the cost of sometimes refusing a product available only on a lower-ranked source. Equal-authority, same-scope disagreements cause abstention rather than a lexical tie-break between values. Values with equivalent numeric formatting or a fee’s additional explanatory caveats do not create a price conflict.

The audit compares the same qualified observation across sources and time. It labels temporal revisions separately in its reasons; a changed legitimate rate is not described as evidence that the old rate was wrong at its observation date. Auto model-year bands are compared only on their overlap at a matching term. Disjoint bands, different terms, different balance tiers and APR versus APY are not contradictions. Historical observations absent from the newest view have no asserted current resolution. The audit includes competing values and evidence; member-facing answers emit only the selected applicable values.

Branch schedules from different branches are not conflicts. The snapshots mostly ground those schedules in dated branch announcements. Answers provide examples, explain that limitation and request the branch; they do not assert a universal current schedule. Unsupported branch names and unpublished loan rates abstain. A missing lost-card replacement fee is not replaced with the distinct rush-delivery fee.

## Validation and limits

There are no API keys or extra packages. Ingestion is roughly linear in the supplied text; per-snapshot indexes trade memory for predictable query latency. All views remain in memory, which is appropriate for this five-snapshot assignment but would need compaction or persistent storage for continuous crawling. The object supports sequential ingestion and read-only queries; concurrent writes are not a supported contract. Schema extraction and intent routing are covered with synthetic temporal, qualifier, source-policy and abstention tests. Public metrics are in VALIDATION.md; the private hidden questions and conflict gold are unavailable.

Two public-evaluation issues are left visible rather than coded around. The all-certificate-rates question has an empty `must_include` list and no expected sources, so the supplied non-LLM scorer assigns it zero regardless of a complete answer. The volunteer question expects the older count for 2023, while the snapshots contain a later explicit count for 2024; the answer reports the newer historical statement and does not relabel it as “last year.” Branch-hour source-credit expectations can also name the homepage/contact page while the actual supporting schedule is in an announcement. The implementation cites the evidence actually used.

Potential next steps are a richer query parser, explicit effective/expiration intervals for all promotional forms, broader narrative fact extraction, and an independently labeled conflict precision/recall evaluation. An optional constrained model could help interpretation, but would add cost, latency and nondeterminism; it is unnecessary to run this submission.

## Untrusted source text

Source content never becomes executable instructions. A conservative ingestion guard quarantines pages containing recognizable prompt-injection directives before any answer route can use them. Detection normalizes common HTML/Unicode obfuscation and checks page titles as well as bodies. This supplements the engine's structural boundary (no model or tool execution from page text); it does not prove factual authenticity or detect every attack. See SECURITY_REVIEW.md for the input review, the answer-contamination issue addressed, and remaining limits.
