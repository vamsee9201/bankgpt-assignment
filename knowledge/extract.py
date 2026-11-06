"""Extract typed rate facts, retaining every table qualifier and source row.

No values or answers are configured here: all values come from ingest().
"""
import re
from .text import clean, norm, authority
from .types import Fact

PERCENT = re.compile(r'(?<!\d)(\d+(?:\.\d+)?)\s*%')


def metric(header):
    h = norm(header)
    if 'yield' in h or 'apy' in h:
        return 'APY'
    if 'apr' in h or 'annual percentage rate' in h:
        return 'APR'
    if 'dividend' in h:
        return 'dividend rate'
    if h in ('rate', 'interest rate'):
        return 'interest rate'
    return None


def domain_for(url, caption, headers, cells):
    text = norm(' '.join([caption, *headers, *cells[:1]]))
    if any('ira type' in norm(h) for h in headers) or re.match(r'(?:Roth|Traditional):', cells[0], re.I):
        return 'retirement'
    if any('certificate' in norm(h) for h in headers) or ('term' in map(norm, headers) and 'dividend' in text):
        return 'certificate'
    if re.search(r'(?:purchase|refinance):.*(?:fixed|conventional)', norm(cells[0])):
        return 'mortgage'
    if re.search(r'recreational|\batv\b|snowmobile|jet ski|\bboat\b|\brv\b', text) or re.search(r'recreational|boat-rv', url):
        return 'recreational loan'
    if 'model year' in text or re.search(r'auto|vehicle', caption, re.I):
        return 'auto'
    if 'card type' in text or 'credit-card' in url or 'visa' in text:
        return 'credit card'
    if 'checking' in text or 'checking' in url:
        return 'checking'
    if 'personal loan' in text or 'personal-loan' in url:
        return 'personal loan'
    if 'account type' in text or 'balance tier' in text or 'saving' in url or 'money market' in text:
        return 'savings'
    if 'home-loan' in url or 'loan amount' in text:
        return 'home equity'
    return 'loan' if 'loan' in text else 'rate'


def extract_tables(page, sid):
    lines = page.markdown.splitlines()
    caption = page.title
    section = page.title
    headers = None
    for i, line in enumerate(lines):
        if not line.strip().startswith('|'):
            headers = None
            text = clean(line)
            if line.startswith('#'):
                section = caption = text
            elif re.match(r'^-?\s*\[[^\]]+Rates[^\]]*\]\(', line, re.I):
                section = caption = text.lstrip('- ')
            elif text and len(text) < 100 and not re.search(r'[.!?]|https?://|\[|\]|^[-_*]|^\d{4}-', line):
                caption = text
            continue
        cells = [clean(c) for c in line.strip().strip('|').split('|')]
        if i + 1 < len(lines) and re.match(r'^\s*\|[ :|-]+\|\s*$', lines[i+1]):
            headers = cells
            continue
        if not headers or len(headers) != len(cells):
            continue
        metrics = [(j, metric(h)) for j, h in enumerate(headers) if metric(h)]
        if not metrics or not any('%' in c for c in cells):
            continue
        domain = domain_for(page.url, caption + ' ' + section, headers, cells)
        product = cells[0]
        first = norm(headers[0])
        qualifiers = []
        if first in ('term', 'term length') and re.fullmatch(r'\d+\s*(?:Months?|Years?)', product, re.I) and domain != 'certificate':
            product = domain
            qualifiers.append(cells[0])
        elif first in ('balance tier', 'balance'):
            product = caption
            qualifiers.append(cells[0])
        elif norm(product) in ('variable interest rate', 'interest rate'):
            product = caption
        for j, h in enumerate(headers):
            if j and any(k in norm(h) for k in ('term', 'balance tier', 'loan amount')) and not metric(h):
                qualifiers.append(cells[j])
        if ('/business/' in page.url or '/business-rates' in page.url) and not norm(product).startswith('business'):
            product = 'Business ' + product
        for j, name in metrics:
            match = PERCENT.search(cells[j])
            if match:
                name = 'APR' if re.search(r'\bAPR\b', cells[j], re.I) else name
                yield Fact(domain, product, tuple(qualifiers), name, match[1] + '%',
                           page.url, sid, line.strip(), authority(page.url), conditions=tuple(
                               f'{headers[k]}: {cells[k]}' for k in range(len(headers))
                               if 'min.' in headers[k].lower() or 'minimum' in headers[k].lower()))


def extract_prose(page, sid):
    """Small semantic schemas for rate ranges and calculator defaults."""
    text = clean(page.markdown)
    # Personal card headings attach an ongoing APR range to the correct card,
    # excluding introductory balance transfers and fees.
    if 'credit-card' in page.url:
        for name, body in re.findall(r'(?:^|\n)###\s+([^\n]+)\n(.*?)(?=\n###?\s|\Z)', page.markdown, re.S):
            for line in body.splitlines():
                if re.search(r'ongoing rate|competitive rate', line, re.I):
                    rates = PERCENT.findall(line)
                    if rates:
                        yield Fact('credit card', clean(name), (), 'APR', '-'.join(v+'%' for v in rates),
                                   page.url, sid, clean(line), authority(page.url))
    # Routing numbers only when explicitly attributed to this credit union.
    for m in re.finditer(r'(?i)routing (?:number|#)\s*:?\s*\(?([0-9]{9})', text):
        yield Fact('identity', 'Routing number', (), 'number', m[1], page.url, sid,
                   text[max(0,m.start()-25):m.end()+30], authority(page.url))
    # A conservative fallback for narrative certificate pages. Term, jumbo qualifier and APY remain distinct.
    if '|' not in page.markdown:
        for line in text.splitlines():
            term = re.search(r'(\d+)[ -]month\b', line, re.I)
            value = PERCENT.search(line)
            if term and value and 'certificate' in line.lower():
                product = f'{term[1]} Month ' + ('Jumbo ' if 'jumbo' in line.lower() else '') + 'Certificate'
                expiry = re.search(r'(?:offer\s+)?(?:ended|ends|expires|valid through)\s+(20\d\d-\d\d-\d\d)', line, re.I)
                name = 'APY' if 'apy' in line.lower() else 'dividend rate'
                yield Fact('certificate', product, (), name, value[1]+'%', page.url, sid, line,
                           authority(page.url), expiry[1] if expiry else None)



def extract(page, sid):
    yield from extract_tables(page, sid)
    yield from extract_prose(page, sid)
    yield from extract_fees(page, sid)


def fact_key(f):
    # Footnotes, punctuation, thousands separators and dash styles are presentation,
    # not a new tier. Do NOT discard numeric qualifiers or business/jumbo markers.
    def key(s):
        s = norm(s).replace(',', '').replace('months', 'month').replace('years', 'year')
        from decimal import Decimal
        s = re.sub(r'\d+(?:\.\d+)?', lambda m: format(Decimal(m[0]).normalize(), 'f'), s)
        s = re.sub(r'\s+account$', '', s)
        return re.sub(r'[^a-z0-9.]+', ' ', s).strip()
    return f.domain, key(f.product), tuple(key(x) for x in f.qualifiers), f.metric


def extract_fees(page, sid):
    if not re.search(r'fee.schedule|/fees(?:/|$)', page.url, re.I) and norm(page.title) != 'fees':
        return
    for raw in page.markdown.splitlines():
        line = clean(raw)
        if line.startswith('|'):
            cells = [x.strip() for x in line.strip('|').split('|')]
            if len(cells) < 2 or not cells[0] or not cells[1]:
                continue
            label, value = cells[:2]
        else:
            match = re.match(r'(.+?)\s+(\$[\d,.]+.*)$', line)
            if not match or len(match[1]) > 130 or match[1].lstrip().startswith(('(', '*', '•')):
                continue
            label, value = match.groups()
        if re.match(r'\$\d|Free\b|Available at no charge|\d+(?:\.\d+)?%', value, re.I):
            yield Fact('fee', label.rstrip(':'), (), 'fee', value, page.url, sid, raw.strip(), 110)


def value_key(f):
    from decimal import Decimal
    if f.domain == 'fee':
        value = re.sub(r'[\\*_]', '', f.value)
        amount = re.match(r'\$([\d,.]+)', value)
        if amount:
            units = re.search(r'per (?:item|month|hour|inquiry|transaction)|each', value, re.I)
            return str(Decimal(amount[1].replace(',', '').rstrip('.')).normalize()), units[0].lower() if units else ''
        return norm(value)
    return re.sub(r'\d+(?:\.\d+)?', lambda m: str(Decimal(m[0]).normalize()), norm(f.value))
