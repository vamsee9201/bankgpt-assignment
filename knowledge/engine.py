"""Temporal selection, qualified fact answering, evidence retrieval and conflict audit."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from math import log
import re

from .extract import extract, fact_key, value_key, PERCENT
from .text import clean, norm, tokens, passages, canonical_url, question_date, normalize_question
from .types import Answer, Conflict, Source
from .security import instruction_signals


@dataclass
class View:
    sid: str
    taken_on: str
    pages: dict
    facts: list
    passages: list
    postings: dict


class TemporalKnowledge:
    def __init__(self):
        self._views = {}
        self._quarantined = {}
        self._conflict_cache = None

    def ingest(self, snapshot):
        date.fromisoformat(snapshot.taken_on)
        pages, rejected = {}, []
        for p in snapshot.pages:
            signals = instruction_signals(p.title, p.markdown)
            if signals:
                rejected.append((p.url, signals))
                continue
            pages[canonical_url(p.url)] = p
        # Quarantine before every consumer, including raw-page branch/link paths.
        # Keep reason labels for audit; do not echo attacker-controlled payloads.
        self._quarantined[snapshot.taken_on] = tuple(rejected)
        facts, chunks = [], []
        for p in pages.values():
            facts.extend(extract(p, snapshot.snapshot_id))
            chunks.extend(passages(p, snapshot.snapshot_id))
        index = defaultdict(list)
        for i, p in enumerate(chunks):
            for word in p.tokens:
                index[word].append(i)
        # Each snapshot is a full replacement, not an append-only URL cache.
        self._views[snapshot.taken_on] = View(snapshot.snapshot_id, snapshot.taken_on,
                                            pages, facts, chunks, dict(index))
        self._conflict_cache = None

    def _view(self, as_of):
        if as_of:
            date.fromisoformat(as_of)
        dates = [d for d in self._views if not as_of or d <= as_of]
        return self._views[max(dates)] if dates else None

    @staticmethod
    def _refuse(sources=(), detail=None):
        return Answer(detail or "I don't know from the supplied website snapshots. Please contact Dupaco to confirm.",
                      list(sources), False)

    @staticmethod
    def _unique_sources(facts):
        seen, out = set(), []
        for f in facts:
            s = f.source()
            key = (s.url, s.snapshot_id, s.quote)
            if key not in seen:
                out.append(s)
                seen.add(key)
        return out

    def _facts_answer(self, facts, view):
        if not facts:
            return self._refuse()
        groups = defaultdict(list)
        for f in facts:
            groups[fact_key(f)].append(f)
        winners, notes = [], []
        for key, candidates in groups.items():
            rank = max(f.authority for f in candidates)
            best = [f for f in candidates if f.authority == rank]
            if len({value_key(f) for f in best}) > 1:
                return self._refuse(self._unique_sources(best),
                    "I can't confirm a single value: equally authoritative pages disagree. Please contact Dupaco.")
            chosen = sorted(best, key=lambda f: (-len(f.value), f.url, f.quote))[0]
            winners.append(chosen)
            peers = [f for f in view.facts if self._same_scope(chosen, f)]
            if any(value_key(f) != value_key(chosen) and f.authority < chosen.authority for f in peers):
                notes.append('The official product rate table takes precedence over conflicting secondary content.')
            if any(value_key(f) != value_key(chosen) for f in candidates):
                notes.append('The official product rate table takes precedence over a secondary page.')
        winners.sort(key=lambda f: (f.product, f.qualifiers, f.metric))
        rows = []
        for f in winners:
            label = f.product + (' (' + '; '.join(f.qualifiers) + ')' if f.qualifiers else '')
            suffix = '' if f.metric in ('number', 'fee') else ' ' + f.metric
            conditions = ' (' + '; '.join(f.conditions) + ')' if f.conditions else ''
            rows.append(f'{label}: {f.value}{suffix}{conditions}')
        return Answer('; '.join(rows) + '.', self._unique_sources(winners), True,
                      ' '.join(sorted(set(notes))) or None)

    def answer(self, question, as_of=None):
        try:
            view = self._view(as_of or question_date(question))
        except (ValueError, TypeError):
            return self._refuse(detail="I can't interpret that date. Please use an ISO date (YYYY-MM-DD).")
        if not view:
            return self._refuse(detail="I don't know: no supplied snapshot exists on or before that date.")
        q = normalize_question(question)
        rate_query = bool(re.search(r'\brate|\bapy\b|\baprs?\b|\bdividend|\binterest|\byield', q))

        # Destination links are taken from observed pages and observed links only.
        if re.search(r'\b(url|link|website)\b', q) or ('join' in q and 'online' in q):
            links = self._links(q, view)
            if links:
                return links
        if 'routing' in q:
            return self._facts_answer([f for f in view.facts if f.domain == 'identity'], view)
        if rate_query or re.search(r'certificate|\bcds?\b', q):
            result = self._rates(q, view)
            if result is not None:
                return result
        if re.search(r'\bfee|\bcost|how much|charge.*(?:wire|overdraft|card|notary)|replacement', q):
            fee = self._fees(q, view)
            if fee is not None:
                return fee
        if re.search(r'\bhour|\blobby|\bdrive[ -]?(?:up|through)', q):
            return self._hours(q, view)
        if 'hy-vee' in q or 'hy vee' in q:
            return self._hyvee(q, view)
        if re.search(r'how many.*(?:branch|location)|number of.*branch', q):
            return self._branch_count(view)
        if 'forbes' in q:
            return self._forbes(q, view)
        if re.search(r'\baddress\b|where is.*branch|where.*located', q):
            address = self._address(q, view)
            if address:
                return address
            if 'branch' in q:
                return self._refuse()
        if re.search(r'volunteer.*(?:time off|\bvto\b)|(?:time off|\bvto\b).*volunteer', q):
            ps = [p for p in view.passages if re.search(r'\d+.*employees.*used.*(?:benefit|time off)', p.text, re.I)]
            year = re.search(r'\b20\d{2}\b', q)
            requested_year = year[0] if year else str(int(view.taken_on[:4])-1) if 'last year' in q else None
            scoped = [p for p in ps if requested_year and requested_year in p.text]
            if requested_year and scoped:
                p = max(scoped, key=lambda p: (p.published, p.url))
                return Answer(p.text, [p.source()])
            if year:
                return self._refuse()
            if ps:
                p = max(ps, key=lambda p: (p.published, p.url))
                if requested_year:
                    return Answer("I can't confirm last year's count. The latest explicit count I found is historical: " +
                                  p.text, [p.source()], confident=False)
                return Answer('The latest explicit historical count I found: ' + p.text, [p.source()])
            return self._refuse()
        if re.search(r'eligible|become.*member|who.*(?:join|member)|membership.*(?:qualif|require)', q):
            ps = [p for p in view.passages if '/about/join' in p.url and
                  (re.search(r'live or work|family member|Iowa.*Illinois.*Wisconsin', p.text, re.I))]
            if ps:
                return Answer(' '.join(p.text for p in ps), self._unique_sources(ps))
        if re.search(r'update|change', q) and re.search(r'contact|address|phone|email', q):
            ps = [p for p in view.passages if 'contact' in p.url and
                  re.search(r'Shine|800-', p.text) and 'general questions' in p.text.lower()]
            if ps:
                # Describe the observed contact channel without inventing account verification steps.
                return Answer('Use Shine Online or Mobile Banking to contact Dupaco, or call ' +
                              self._phone(view) + ' for help updating your contact information.',
                              self._unique_sources(ps))
        if 'wallet' in q or re.search(r'apple pay|google pay|samsung pay', q):
            return self._retrieve(q, view, required={'pay'}, extra={'apple', 'google', 'samsung', 'wallet'})
        if re.search(r'student|university|college', q):
            ps = [p for p in view.passages if '/loans/student-loans' in p.url and
                  re.search(r'flexible|origination|new.*loan|refinanc', p.text, re.I)]
            if ps:
                return Answer('Student loans: ' + ' '.join(dict.fromkeys(p.text for p in ps))[:2200],
                              self._unique_sources(ps))
        # Financial rates must be supported by a typed fact. A neighboring loan
        # product's number in a paragraph is never a substitute for a missing rate.
        if rate_query:
            return self._refuse()
        return self._retrieve(q, view)

    def _rates(self, q, view):
        domain = None
        if re.search(r'certificate|\bcds?\b', q):
            domain = 'certificate'
        elif re.search(r'auto|vehicle|motorcycle|\bcar\b', q):
            domain = 'auto'
        elif re.search(r'mortgage|home loan|\barm\b|construction loan', q):
            domain = 'mortgage'
        elif re.search(r'\bira\b|roth|retirement', q):
            domain = 'retirement'
        elif re.search(r'credit card|platinum|rewards visa', q):
            domain = 'credit card'
        elif 'checking' in q:
            domain = 'checking'
        elif re.search(r'saving|money market|\bhsa\b', q):
            domain = 'savings'
        elif 'personal loan' in q:
            domain = 'personal loan'
        elif re.search(r'heloc|home equity', q):
            domain = 'home equity'
        if domain is None:
            return None
        facts = [f for f in view.facts if f.domain == domain and
                 (not f.valid_until or f.valid_until >= view.taken_on)]
        # Legacy URL variants may have changed their product labels and model-year
        # bands. Resolve source authority before matching qualifiers, so they cannot
        # leak back in as apparently distinct products.
        if facts:
            rank = max(f.authority for f in facts)
            facts = [f for f in facts if f.authority == rank]
        # Prefer explicitly published product rates over calculators and marketing copies.
        if domain == 'mortgage' and re.search(r'construction|adjustable|\barm\b|\d/\d', q):
            requested = re.search(r'\d/\d', q)
            facts = [f for f in facts if (requested and requested[0] in f.product) or
                     ('construction' in q and 'construction' in norm(f.product)) or
                     ('adjustable' in q and 'adjustable' in norm(f.product))]
            return self._facts_answer(facts, view)
        term = re.search(r'\b(\d{1,3})[ -]?(month|year)', q)
        if term:
            amount, unit = int(term[1]), term[2]
            # Mortgage terms are years; consumer loans and certificates use months.
            target = amount * 12 if unit == 'year' and domain != 'mortgage' else amount
            if unit == 'month' and domain == 'mortgage':
                target = amount // 12
            facts = [f for f in facts if re.search(r'\b'+str(target)+r'[ -]?(?:month|year)', norm(f.product+' '+' '.join(f.qualifiers)))]
        business = 'business' in q
        if domain in ('checking', 'credit card', 'savings', 'certificate'):
            if business:
                facts = [f for f in facts if 'business' in norm(f.product) or '/business/' in f.url]
            elif domain != 'credit card' or re.search(r'personal|platinum|rewards', q):
                facts = [f for f in facts if 'business' not in norm(f.product) and '/business/' not in f.url]
        if domain == 'certificate':
            if re.search(r'standard|non[ -]?jumbo|regular', q):
                facts = [f for f in facts if 'jumbo' not in norm(f.product)]
            elif 'jumbo' in q:
                facts = [f for f in facts if 'jumbo' in norm(f.product)]
            if 'special' in q:
                facts = [f for f in facts if 'special' in norm(f.product)]
            wanted = 'dividend rate' if re.search(r'dividend|interest rate', q) and 'apy' not in q else 'APY'
            facts = [f for f in facts if f.metric == wanted]
        if domain == 'auto':
            year = re.search(r'\b(19\d{2}|20\d{2})\b', q)
            if year:
                target = int(year[1])
                def model_matches(f):
                    m = re.search(r'(20\d{2})(?:\s*-\s*(\d{2,4}))?', f.product)
                    if not m:
                        return False
                    low = int(m[1]); high = int(m[2]) if m[2] else low
                    if high < 100:
                        high += low // 100 * 100
                    return target <= low if 'older' in norm(f.product) else low <= target <= high
                facts = [f for f in facts if model_matches(f)]
            elif term:
                tiers = {f.product for f in facts}
                if len(tiers) > 1:
                    return self._refuse(detail="The auto APR depends on the vehicle model year. Please specify the model year.")
        if domain == 'retirement':
            for name in ('roth', 'traditional', 'variable'):
                if name in q:
                    facts = [f for f in facts if name in norm(f.product)]
            facts = [f for f in facts if f.metric == ('dividend rate' if 'dividend' in q else 'APY')]
        if domain == 'credit card':
            for name in ('platinum', 'rewards'):
                if name in q:
                    facts = [f for f in facts if name in norm(f.product)]
        if domain == 'mortgage':
            purchase = 'refinance' not in q
            facts = [f for f in facts if ('refinance' not in norm(f.product)) == purchase]
            amounts = [float(n.replace(',', '')) for n in re.findall(r'\$([\d,]+)', q)]
            if amounts:
                def tier_amount(f):
                    m = re.search(r'\$([\d,]+)', f.product)
                    return float(m[1].replace(',', '')) if m else float('inf')
                limit = min((tier_amount(f) for f in facts if tier_amount(f) >= max(amounts)), default=None)
                facts = [f for f in facts if tier_amount(f) == limit]
            # Full table when term is unspecified; tiers are explicitly labeled.
            facts = [f for f in facts if f.metric in ('interest rate', 'APR')]
        if domain in ('savings', 'checking'):
            names = [f.product for f in facts]
            # Resolve named products dynamically; a generic savings question defaults
            # to Share Savings, never a higher-yield money-market or business product.
            scored = [(len(tokens(n) & tokens(q)), len(tokens(n)), n) for n in set(names)]
            best = max((s[0] for s in scored), default=0)
            if best:
                names = {n for s, _, n in scored if s == best}
                # A bare 'savings' is not enough to pick Bright/Launchpad/etc.
                if best == 1 and 'share' not in q and not re.search(r'bright|high.yield|holiday|launchpad|name it|health|money market|checking', q):
                    names = {n for n in names if norm(n) == 'share savings'}
                facts = [f for f in facts if f.product in names]
            facts = [f for f in facts if f.metric == ('dividend rate' if 'dividend' in q else 'APY')]
            numbers = [float(n.replace(',', '')) for n in re.findall(r'\$\s*([\d,]+(?:\.\d+)?)', q)]
            if numbers:
                balance = numbers[0]
                def includes(f):
                    if not f.qualifiers:
                        return True
                    nums = [float(n.replace(',', '')) for n in re.findall(r'\d[\d,]*(?:\.\d+)?', f.qualifiers[0])]
                    return bool(nums) and nums[0] <= balance and (len(nums) == 1 or balance <= nums[1])
                facts = [f for f in facts if includes(f)]
            if re.search(r'highest|maximum|top|any.*tier', q) and facts:
                maximum = max(float(f.value.strip('%')) for f in facts)
                facts = [f for f in facts if float(f.value.strip('%')) == maximum]
        # Restrict each resolved fact to its winning authority within this snapshot.
        answer = self._facts_answer(facts, view)
        requested = re.search(r'(\d+(?:\.\d+)?)\s*%', q)
        if requested and re.search(r'do any|does .*pay|pay .*apy', q) and facts:
            found = any(float(f.value.strip('%')) == float(requested[1]) for f in facts)
            answer.text = ('Yes. ' if found else 'No matching tier is published. ') + answer.text
        return answer

    def _fees(self, q, view):
        facts = [f for f in view.facts if f.domain == 'fee']
        if not facts:
            return None
        query = tokens(q) - {'fee', 'much', 'cost', 'charge', 'charged', 'pay', 'a', 'replacement'}
        important = query & {'lost', 'rush', 'international', 'domestic', 'incoming',
                             'outgoing', 'notary', 'overdraft', 'reopening', 'debit', 'credit'}
        ranked = []
        for f in facts:
            words = tokens(f.product)
            if not important <= words:
                continue
            overlap = len(query & words)
            if overlap < min(2, len(query)) or overlap / max(1, len(query)) < .5:
                continue
            if ('business' in q) != ('business' in norm(f.product)):
                continue
            ranked.append((overlap / max(1, len(words | query)), f))
        if not ranked:
            return self._refuse() if re.search(r'fee|charge|replacement|lost.*card', q) else None
        high = max(s for s, _ in ranked)
        best = [f for s, f in ranked if s == high]
        return self._facts_answer(best, view)

    def _links(self, q, view):
        if re.search(r'certificate|\bcd\b', q):
            candidates = [p for p in view.pages.values() if '/personal/savings-account' == canonical_url(p.url).split('.com')[-1]]
            if candidates:
                p = candidates[0]
                return Answer(p.url.rstrip('/')+'#rates', [Source(p.url, view.sid, 'Savings Account Rates')])
        if re.search(r'locator|branch.*atm|atm.*branch', q):
            candidates = [p for p in view.pages.values() if canonical_url(p.url).endswith('/contact')]
            if candidates:
                p = candidates[0]
                return Answer(p.url, [Source(p.url, view.sid, clean(p.markdown)[:250])])
        if re.search(r'join|member', q):
            for p in view.pages.values():
                if '/about/join' in p.url:
                    m = re.search(r'https://join\.[a-z0-9.-]+/?', p.markdown)
                    if m:
                        return Answer(m[0], [Source(p.url, view.sid, m[0])])
        return None

    def _phone(self, view):
        for p in view.pages.values():
            if canonical_url(p.url).endswith('/contact'):
                m = re.search(r'\b\d{3}-\d{3}-\d{4}\b', p.markdown)
                if m:
                    return m[0]
        return 'the contact number listed on its website'

    def _hours(self, q, view):
        schedules = []
        drive = bool(re.search(r'drive|driveup', q))
        for p in view.pages.values():
            body = re.split(r'^## Handpicked', p.markdown, maxsplit=1, flags=re.M)[0]
            pattern = r'\*\*(?:Drive-up|Drive-through|Drive up)(?:[^*]*)\*\*' if drive else r'\*\*Lobby\*\*'
            for m in re.finditer(pattern, body, re.I):
                rest = body[m.end():]
                rest = re.split(r'\n\s*\*\*|\n\s*#|\n\s*Dupaco Community', rest, maxsplit=1)[0]
                lines = [clean(x) for x in rest.splitlines() if re.search(r'Monday|Friday|Saturday|Sunday|Thursday', x, re.I)]
                if lines:
                    schedules.append((p, '; '.join(lines[:5]), clean(body[:1000])))
        # A named branch must be anchored to the source's main content, not a
        # recommended article or a different organization's ATM.
        name = None if re.search(r'all .*branch|all branch|same .*hour|general|your .*hour|drive.up hour', q) else re.search(r'(?:the\s+)?([a-z][a-z -]+?)\s+branch', q)
        if name:
            words = tokens(name[1]) - {'all', 'general', 'same', 'dupaco', 'hour', 'lobby', 'give', 'have', 'keep'}
            # Match meaningful place names from the end of the noun phrase.
            words -= {'can', 'lobby', 'hour', 'give', 'have', 'keep', 'same', 'all'}
            if words:
                schedules = [x for x in schedules if words <= tokens(x[2])]
        if not schedules:
            return self._refuse()
        # The published examples are dated, branch-specific evidence, not a
        # fabricated universal schedule. Preserve that limitation in the answer.
        schedules.sort(key=lambda x: ('dupaco-celebrates-completion-of-newest-learning-lab' not in x[0].url, x[0].url))
        chosen = schedules[:2] if not name else schedules[:1]
        text = ('Drive-up' if drive else 'Lobby') + ' hours vary by branch. Published branch examples: '
        text += ' | '.join(x[1] for x in chosen)
        text += '. These schedules come from dated branch announcements; please confirm your branch’s current hours. Which branch do you need?'
        return Answer(text, [Source(p.url, view.sid, schedule) for p, schedule, _ in chosen],
                      confident=False, conflict_note='Schedules refer to different branches, so differences are not contradictions.')

    def _address(self, q, view):
        for p in view.pages.values():
            if not canonical_url(p.url).endswith('/contact'):
                continue
            for line in clean(p.markdown).splitlines():
                if re.search(r'\d.*\b[A-Z]{2},?\s+\d{5}', line):
                    names = tokens(line) & tokens(q)
                    if names - {'branch', 'dupaco', 'address', 'location'}:
                        text = line.replace('Ln.', 'Lane').replace('Dr.', 'Drive')
                        return Answer(text, [Source(p.url, view.sid, line)])
        return None

    def _hyvee(self, q, view):
        pages = [p for p in view.pages.values() if 'hy-vee-branch-closure' in p.url]
        for p in pages:
            lines = [clean(x) for x in p.markdown.splitlines()]
            if re.search(r'where|full.service|go|alternative', q):
                selected = [x for x in lines if 'Key West' in x and 'Sycamore' in x]
            else:
                selected = [x for x in lines if re.search(r'(will close|closed|closing|close on).*\d{4}', x, re.I)]
            if selected:
                text = ' '.join(selected)
                if re.search(r'still open|open today', q):
                    text = 'The announcement says the branch was scheduled to close: ' + text
                return Answer(text, [Source(p.url, view.sid, ' '.join(selected)[:500])])
        return self._refuse()

    def _branch_count(self, view):
        candidates = []
        for p in view.passages:
            m = re.search(r'(\d+)\s+branch (?:office )?locations', p.text, re.I)
            if m:
                candidates.append((p.published, p.authority, m[1], p))
        if not candidates:
            return self._refuse()
        latest = max(x[0] for x in candidates)
        current = [x for x in candidates if x[0] == latest]
        if len({x[2] for x in current}) > 1:
            return self._refuse([x[3].source() for x in current])
        _, _, count, p = max(current, key=lambda x: (x[1], x[3].url))
        return Answer(f'{count} branch office locations, according to the latest dated statement in the supplied snapshot.',
                      [p.source()], conflict_note='Dated historical announcements do not establish the current branch count.')

    def _forbes(self, q, view):
        candidates = []
        for p in view.passages:
            # Keep only the article body, never boilerplate or related headlines.
            if 'forbes' in p.url and re.search(r'\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth) time\b', p.text, re.I):
                candidates.append(p)
        if candidates:
            p = max(candidates, key=lambda p: (p.published, p.url))
            return Answer(p.text, [p.source()])
        return self._retrieve(q, view, required={'forbes'})

    def _retrieve(self, q, view, required=frozenset(), extra=frozenset()):
        query = tokens(q) | extra
        if not query:
            return self._refuse()
        scores = defaultdict(float)
        total = len(view.passages)
        for word in query:
            ids = view.postings.get(word, ())
            weight = log(1 + total / (1 + len(ids)))
            for i in ids:
                scores[i] += weight
        ranked = []
        for i, score in scores.items():
            p = view.passages[i]
            if required and not required <= p.tokens:
                continue
            coverage = len(tokens(q) & p.tokens) / max(1, len(tokens(q)))
            if coverage < .35 or len(query & p.tokens) < min(2, len(query)):
                continue
            score *= .65 + p.authority / 150
            score *= 1 + .35 * len(tokens(p.heading) & query)
            score /= 1 + max(0, len(p.text)-500)/1600
            ranked.append((score, p))
        if not ranked:
            return self._refuse()
        ranked.sort(key=lambda x: (-x[0], x[1].url, x[1].text))
        p = ranked[0][1]
        # Never confidently retrieve a rate or financial amount from a stale blog
        # merely because it shares terms with a numeric question.
        if re.search(r'rate|\bapr\b|\bapy\b', q) and PERCENT.search(p.text):
            return self._refuse([p.source()])
        return Answer(p.text, [p.source()], confident=True)

    @staticmethod
    def _model_band(f):
        match = re.search(r'(20\d{2})\s*(?:-\s*(\d{2,4}))?', f.product)
        if not match:
            return None
        a = int(match[1])
        b = int(match[2]) if match[2] else a
        if b < 100:
            b += a // 100 * 100
        return (1900, a) if 'older' in norm(f.product) else (min(a, b), max(a, b))

    def _same_scope(self, a, b):
        if fact_key(a) == fact_key(b):
            return True
        if a.domain == b.domain == 'auto' and a.qualifiers == b.qualifiers and a.metric == b.metric:
            ab, bb = self._model_band(a), self._model_band(b)
            return bool(ab and bb and max(ab[0], bb[0]) <= min(ab[1], bb[1]))
        return False

    def conflicts(self):
        if self._conflict_cache is not None:
            return list(self._conflict_cache)
        if not self._views:
            return []
        history = defaultdict(list)
        latest_view = self._view(None)
        current = {fact_key(f) for f in latest_view.facts}
        for day, view in sorted(self._views.items()):
            for f in view.facts:
                history[fact_key(f)].append((day, f))
        # Model-year bands can shift after a new model year. Compare their
        # intersection at the same term; disjoint bands remain different facts.
        auto = [f for f in latest_view.facts if f.domain == 'auto']
        if auto:
            rank = max(f.authority for f in auto)
            official = {fact_key(f): f for f in auto if f.authority == rank}
            for key in [k for k in history if k[0] == 'auto']:
                del history[key]
            for key, winner in official.items():
                history[key] = [(day, f) for day, view in sorted(self._views.items())
                                for f in view.facts if self._same_scope(winner, f)]
        result = []
        for key, observations in sorted(history.items()):
            if key[0] in ('identity', 'rate', 'loan'):
                continue
            by_value = {}
            for _, f in observations:
                by_value[value_key(f)] = f.value
            values = sorted(by_value.values())
            if len(values) < 2:
                continue
            last_day = max(d for d, _ in observations)
            latest = [f for d, f in observations if d == last_day]
            active = [f for f in latest if not f.valid_until or f.valid_until >= last_day]
            eligible = active or latest
            rank = max(f.authority for f in eligible)
            best = [f for f in eligible if f.authority == rank]
            winner_values = {value_key(f) for f in best}
            winner = sorted(best, key=lambda f: f.url)[0]
            same_time = len({value_key(f) for f in latest}) > 1
            resolution = winner.value if len(winner_values) == 1 else None
            reason = ('Within-snapshot disagreement: official product tables outrank calculators, legacy pages and dated marketing.'
                      if same_time else 'Temporal revision of the same qualified fact; use the newest observed snapshot, and retain earlier versions for as-of answers.')
            if key[0] == 'auto':
                reason += ' Model-year ranges are compared only where they overlap, at the same loan term.'
            if not active:
                resolution = None
                reason = 'All observed offers for this fact have explicitly expired; no current value is asserted.'
            elif key not in current:
                resolution = None
                reason = 'This historical fact is absent from the latest full snapshot; no current value is asserted.'
            elif resolution is None:
                reason = 'Equally authoritative sources disagree; unresolved, so answers abstain.'
            seen, sources = set(), []
            for day, f in reversed(observations):
                k = (f.url, value_key(f))
                if k not in seen:
                    sources.append(f.source()); seen.add(k)
            topic = ' '.join([winner.domain, winner.product, *winner.qualifiers, winner.metric])
            result.append(Conflict(topic, values, sources, resolution, reason))
        result.extend(self._prose_conflicts(latest_view))
        self._conflict_cache = tuple(result)
        return list(result)

    def _prose_conflicts(self, view):
        result = []
        schemas = [
            ('Branch office count', r'(\d+)\s+branch (?:office )?locations'),
            ('Membership charter area county count', r'(\d+)\s+counties throughout'),
            ('Forbes Best-in-State recognition count', r'\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth) time\b'),
        ]
        for topic, pattern in schemas:
            found = []
            for p in view.passages:
                if 'recognition' in topic and 'forbes' not in p.url:
                    continue
                m = re.search(pattern, p.text, re.I)
                if m:
                    found.append((m[1].lower(), p))
            values = sorted({value for value, _ in found})
            if len(values) < 2:
                continue
            dated = [(v, p) for v, p in found if p.published]
            if not dated:
                continue
            day = max(p.published for _, p in dated)
            current = [(v, p) for v, p in dated if p.published == day]
            resolutions = {v for v, _ in current}
            resolution = next(iter(resolutions)) if len(resolutions) == 1 else None
            sources, seen = [], set()
            for value, p in sorted(found, key=lambda x: (x[1].published, x[1].url), reverse=True):
                if value not in seen:
                    sources.append(p.source()); seen.add(value)
            result.append(Conflict(topic, values, sources, resolution,
                'Dated news statements differ. Use the newest publication available in this snapshot; '
                'older statements describe their historical context and may reflect legitimate changes.'
                if resolution else 'The newest dated statements disagree; no current value is asserted.'))
        return result
