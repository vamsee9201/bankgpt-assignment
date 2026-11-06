"""Organizer entry point. No network access, models, keys, or import-time data reads."""
from knowledge.engine import TemporalKnowledge


def build():
    return TemporalKnowledge()
