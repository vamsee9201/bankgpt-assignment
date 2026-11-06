# Prompt-injection review

Reviewed the supplied participant ZIP and matching standalone assignment PDF on November 6, 2026. This is a bounded static review and adversarial regression check, not a guarantee that every possible attack has been ruled out.

## Input findings

- Recursively inspected six ZIP containers: the participant archive and five snapshot archives. Inspected 3,316 non-ZIP file entries, including 3,294 website page versions and four synthetic harness-fixture pages.
- Searched readable content for instruction overrides, assistant-targeted directives, role impersonation, secret-extraction language, concealment instructions and common execution hints. No matches were found by those searches. Reviewed the supplied scorer/starter code separately.
- Found directional Unicode controls in 158 page versions. Inspection places them around Arabic/Hebrew country names in phone-country menus; these are not evidence of an injection. Directionality characters alone are not grounds for rejection.
- The five-page assignment PDF is byte-identical to the copy in the kit. No document open/additional actions, page additional actions, non-URL annotation actions, embedded attachments or suspicious instruction-override text were found in the inspected PDF structures/text.
- No archive paths with absolute locations or parent traversal were found. The solution's dataset reader independently rejects unsafe relative paths and resolves directory inputs within their snapshot root.

Participant ZIP SHA-256: `9574d1ade39d2edd97f066176997f75f0ae017693b6307b7ad7fd8d8c22a941b`.

## Runtime boundary and change

Source pages are untrusted evidence. They cannot change application policy, start a shell, call tools, fetch live websites or read credentials: the answer engine has none of those execution capabilities, and uses no language model. Developer-controlled code determines source precedence and historical selection. A source calling itself authoritative does not change its rank.

The review identified a separate answer-contamination risk: an unstructured retrieval fallback could quote instruction-like source text as if it answered a member's question. Added a conservative ingestion quarantine in `knowledge/security.py`. Pages with recognizable override, role-spoofing, assistant-directed, secret-extraction or concealment payloads are excluded before fact extraction, indexing and all raw-page answer routes. Titles are checked too. HTML entities, Unicode compatibility forms and invisible format characters are normalized for detection. Only URL/reason metadata is retained for rejected pages; attack payloads are not copied into an answer or citation. This trades recall for caution when a page mixes valid data with an obvious attack.

Nine adversarial regression tests exercise contaminated rate tables, retrieval echoing, forged system/developer roles, title payloads, entity/invisible-character obfuscation, secret-extraction directives, raw-page link selection, benign member instructions/bidi text, and recovery in a later clean snapshot. They augment the original 30 functional tests.

## Limits

Pattern detection is defense in depth. It can miss novel, encoded, multilingual or indirect attacks and can reject benign pages that discuss them. It does not authenticate the factual content of a rate table. Plausible false facts without instruction-like language remain a data-poisoning risk; provenance, qualifiers, source precedence and abstention reduce that risk but do not eliminate it.

The organizer's optional `--judge` mode sends candidate text to an external model; it is a separate instruction-following surface. This submission's recorded evaluations do not enable that mode. The supplied harness was not changed. Reproduction wrapper execution of a Python scorer assumes the user explicitly trusts that local code; website text is never executed as code.

The snapshots and private scan/evaluation outputs remain excluded from the public repository. See VALIDATION.md for the post-change functional evaluation.
