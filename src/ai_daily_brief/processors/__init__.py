from .deduplicator import deduplicate
from .rules import classify, editorial_entity, editorial_priority, rank

__all__ = ["deduplicate", "classify", "editorial_entity", "editorial_priority", "rank"]
