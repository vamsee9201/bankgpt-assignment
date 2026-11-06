"""Conservative detection of instruction-like payloads in untrusted source pages.

This is defense in depth, not proof that a page's factual claims are genuine.
The runtime has no model, shell, network or tool execution path for page text.
"""
import html
import re
import unicodedata


_RULES = (
    ('instruction override', re.compile(
        r'\b(?:ignore|disregard|forget|override)\b[^\n]{0,90}'
        r'\b(?:previous|prior|above|system|developer|all)\b[^\n]{0,45}'
        r'\b(?:instructions?|prompts?|messages?)\b', re.I)),
    ('role impersonation', re.compile(
        r'<\|(?:im_start|im_end|system|assistant|developer)\b|'
        r'\[/?INST\]|(?:^|\n)\s*(?:SYSTEM|DEVELOPER)\s*:', re.I)),
    ('assistant-targeted directive', re.compile(
        r'\b(?:if you are|attention|instructions? for|note to)\b[^\n]{0,50}'
        r'\b(?:an? ai|assistant|chatgpt|language model|coding agent)\b', re.I)),
    ('secret extraction directive', re.compile(
        r'\b(?:reveal|exfiltrate|print|send|upload)\b[^\n]{0,65}'
        r'\b(?:system prompt|developer message|api keys?|secret tokens?|environment variables)\b', re.I)),
    ('concealment directive', re.compile(
        r'\bdo not (?:tell|inform) the (?:user|developer)\b', re.I)),
)


def instruction_signals(*fields):
    """Return reason labels only; never run, fetch, or decode executable content.

    NFKC, HTML entities and format-character removal make common visual
    obfuscations comparable. Bidi text alone is not considered malicious.
    """
    text = html.unescape(html.unescape('\n'.join(fields)))
    text = unicodedata.normalize('NFKC', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    return tuple(reason for reason, pattern in _RULES if pattern.search(text))
