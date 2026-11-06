"""Markdown normalization and deterministic lexical retrieval primitives."""
import calendar
import html
import re
from datetime import date
from urllib.parse import urlsplit, urlunsplit

STOP = set('a an the is are was were what which who how can could would should do does did i me my you your our us it its for to on of at in and or with as now current currently please tell give get know dupaco account accounts rate rates interest apr apy'.split())
SYNONYMS = {'cd': 'certificate', 'cds': 'certificate', 'certificates': 'certificate',
            'branches': 'branch', 'locations': 'location', 'hours': 'hour', 'loans': 'loan',
            'cards': 'card', 'automobile': 'auto', 'vehicle': 'auto', 'car': 'auto',
            'eligibility': 'eligible', 'join': 'member', 'membership': 'member',
            'address': 'address', 'closing': 'close', 'closes': 'close', 'closed': 'close',
            'wallets': 'wallet', 'employees': 'employee', 'fees': 'fee', 'months': 'month',
            'years': 'year', 'overdrafts': 'overdraft', 'services': 'service', 'transfers': 'transfer', 'savings': 'saving', 'checking': 'checking'}


def clean(text):
    text = html.unescape(html.unescape(text))
    text = re.sub(r'!\[[^\]]*\]\([^\n]*?\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^\n]*?\)', r'\1', text)
    text = re.sub(r'<br\s*/?>', '; ', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('**', '').replace('\\#', '#').replace('\u00a0', ' ')
    text = text.replace('–', '-').replace('—', '-')
    return re.sub(r'[ \t]+', ' ', text).strip(' #\t\r\n')


def norm(text):
    return re.sub(r'\s+', ' ', clean(text).lower()).strip()


def normalize_question(text):
    names = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
             'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'twelve': 12,
             'fifteen': 15, 'seventeen': 17, 'eighteen': 18, 'twenty': 20,
             'thirty': 30, 'thirty-six': 36, 'forty-eight': 48, 'sixty': 60,
             'seventy-two': 72, 'eighty-four': 84}
    for word in sorted(names, key=len, reverse=True):
        text = re.sub(r'\b'+word+r'(?=[ -]+(?:months?|years?)\b)', str(names[word]), text, flags=re.I)
    return norm(text)


def tokens(text):
    return frozenset(SYNONYMS.get(w, w) for w in re.findall(r'[a-z0-9]+', norm(text)) if w not in STOP)


def canonical_url(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip('/'), p.query, ''))


def authority(url):
    path = urlsplit(url).path
    if '/calculators/' in path or 'calculator' in path:
        return 10
    if 'newsroom' in path or '/learn/' in path or '/blog/' in path:
        return 25
    if path.endswith('.pdf') or '/hubfs/' in path:
        return 45
    if '/personal/' in path or '/business/' in path:
        return 100 if not path.endswith('/') else 70
    if path.startswith('/about') or path in ('/contact', ''):
        return 90
    if 'info.' in url:
        return 20
    return 60


def publication(text):
    # The first article dateline, before recommendations, is the publication date.
    months = '|'.join(calendar.month_name[1:]) + '|' + '|'.join(calendar.month_abbr[1:])
    m = re.search(r'\b('+months+r')\s+(\d{1,2}),?\s+(20\d\d)\b', text[:1800], re.I)
    if not m:
        return ''
    names = {x.lower(): i for i, x in enumerate(calendar.month_name) if x}
    names.update({x.lower(): i for i, x in enumerate(calendar.month_abbr) if x})
    try:
        return date(int(m[3]), names[m[1].lower()], int(m[2])).isoformat()
    except ValueError:
        return ''


def question_date(question):
    m = re.search(r'\b(?:as of|as at|back in|in)\s+(20\d\d-\d\d-\d\d)\b', question, re.I)
    if m:
        return m[1]
    months = '|'.join(calendar.month_name[1:]) + '|' + '|'.join(calendar.month_abbr[1:])
    m = re.search(r'\b(?:as of|as at|back in)\s+('+months+r')\s+(?:(\d{1,2}),?\s+)?(20\d\d)\b', question, re.I)
    if m:
        names = {x.lower(): i for i, x in enumerate(calendar.month_name) if x}
        names.update({x.lower(): i for i, x in enumerate(calendar.month_abbr) if x})
        month, year = names[m[1].lower()], int(m[3])
        return date(year, month, int(m[2]) if m[2] else calendar.monthrange(year, month)[1]).isoformat()
    return None


def passages(page, sid):
    """Keep headings with paragraphs; discard navigation, images and related-article teasers."""
    from .types import Passage
    heading = page.title
    pub = publication(clean(page.markdown))
    body = re.split(r'^#{1,6}\s+(?:Handpicked|Related|Recommended|You May Also)', page.markdown, maxsplit=1, flags=re.M | re.I)[0]
    for block in re.split(r'\n\s*\n', body):
        if block.lstrip().startswith('#') and '\n' not in block.strip():
            heading = clean(block)
            continue
        text = clean(block)
        if len(text) < 18 or 'data points:' in text or len(text) > 3500 or text.startswith('|'):
            continue
        yield Passage(page.url, page.title, heading, text, sid, pub,
                      authority(page.url), tokens(page.title + ' ' + heading + ' ' + text))
