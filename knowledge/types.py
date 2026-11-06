"""Standalone, duck-typed equivalents of the organizer's boundary objects."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Source:
    url: str
    snapshot_id: Optional[str] = None
    quote: Optional[str] = None


@dataclass
class Answer:
    text: str
    sources: list[Source] = field(default_factory=list)
    confident: bool = True
    conflict_note: Optional[str] = None


@dataclass
class Conflict:
    topic: str
    values: list[str]
    sources: list[Source]
    resolution: Optional[str] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class Fact:
    domain: str
    product: str
    qualifiers: tuple[str, ...]
    metric: str
    value: str
    url: str
    snapshot_id: str
    quote: str
    authority: int
    valid_until: Optional[str] = None
    conditions: tuple[str, ...] = ()

    @property
    def key(self):
        return self.domain, self.product, self.qualifiers, self.metric

    def source(self):
        return Source(self.url, self.snapshot_id, self.quote)


@dataclass(frozen=True)
class Passage:
    url: str
    title: str
    heading: str
    text: str
    snapshot_id: str
    published: str
    authority: int
    tokens: frozenset[str]

    def source(self):
        return Source(self.url, self.snapshot_id, self.text[:500])

# The scorer's repeat pass uses isinstance(Answer), so reuse its exact classes
# when it has already installed contract on sys.path. Standalone use needs no kit.
try:
    from contract import Answer, Conflict, Source
except ImportError:
    pass
