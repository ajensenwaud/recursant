"""Pluggable PII detection backends.

Provides two implementations:
- RegexPiiDetector: fast, lightweight, no ML dependencies (default)
- PresidioPiiDetector: ML-based NER via Microsoft Presidio (optional)

The backend is selected via ``RedactionConfig.backend``.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class PiiMatch:
    """A single PII detection result."""
    entity_type: str  # e.g. "email", "credit_card", "PERSON"
    text: str  # the matched text
    start: int  # character offset in the scanned string
    end: int
    score: float = 1.0  # confidence (regex=1.0, NER varies)


class PiiDetector(ABC):
    """Abstract PII detector — detect PII entities in a text string."""

    @abstractmethod
    def detect(self, text: str) -> list[PiiMatch]:
        """Return all PII matches found in *text*."""


# ---------------------------------------------------------------------------
# Regex backend (default)
# ---------------------------------------------------------------------------

# Default patterns — ordered most specific first to avoid greedy overlaps.
DEFAULT_PATTERNS_ORDERED: list[tuple[str, str]] = [
    ("credit_card", r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
    ("ssn", r"\b\d{3}-\d{2}-\d{4}\b"),
    ("ip_address", r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    ("email", r"[\w.-]+@[\w.-]+\.\w+"),
    ("uk_postcode", r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b"),
    ("phone", r"\+\d[\d\s\-()]{7,}\d"),
]


class RegexPiiDetector(PiiDetector):
    """Regex-based PII detection — lightweight, no ML dependencies."""

    def __init__(self, custom_patterns: dict[str, str] | None = None):
        self._patterns: list[tuple[str, re.Pattern]] = []
        for name, pattern in DEFAULT_PATTERNS_ORDERED:
            self._patterns.append((name, re.compile(pattern, re.IGNORECASE)))
        if custom_patterns:
            for name, pattern in custom_patterns.items():
                self._patterns.append((name, re.compile(pattern, re.IGNORECASE)))

    def detect(self, text: str) -> list[PiiMatch]:
        matches: list[PiiMatch] = []
        for entity_type, pattern in self._patterns:
            for m in pattern.finditer(text):
                matches.append(PiiMatch(
                    entity_type=entity_type,
                    text=m.group(),
                    start=m.start(),
                    end=m.end(),
                    score=1.0,
                ))
        return matches


# ---------------------------------------------------------------------------
# Presidio backend (optional — requires presidio-analyzer + spacy)
# ---------------------------------------------------------------------------

class PresidioPiiDetector(PiiDetector):
    """ML-based PII detection via Microsoft Presidio.

    Lazily imports and initializes the Presidio AnalyzerEngine on first use.
    Falls back to regex if Presidio is not installed.
    """

    # Default entity types to detect
    DEFAULT_ENTITIES = [
        "CREDIT_CARD", "CRYPTO", "EMAIL_ADDRESS", "IBAN_CODE",
        "IP_ADDRESS", "NRP", "LOCATION", "PERSON", "PHONE_NUMBER",
        "MEDICAL_LICENSE", "US_SSN", "UK_NHS", "US_BANK_NUMBER",
        "US_DRIVER_LICENSE", "US_ITIN", "US_PASSPORT",
    ]

    def __init__(
        self,
        score_threshold: float = 0.5,
        entities: list[str] | None = None,
    ):
        self._score_threshold = score_threshold
        self._entities = entities or self.DEFAULT_ENTITIES
        self._analyzer: Any = None
        self._available: bool | None = None

    def _ensure_analyzer(self) -> bool:
        """Lazy-load the Presidio analyzer. Returns True if available."""
        if self._available is not None:
            return self._available

        try:
            from presidio_analyzer import AnalyzerEngine
            self._analyzer = AnalyzerEngine()
            self._available = True
            logger.info("presidio_analyzer_loaded")
        except ImportError:
            logger.warning("presidio_not_installed", msg="Falling back to regex PII detection")
            self._available = False
        except Exception as e:
            logger.warning("presidio_init_failed", error=str(e))
            self._available = False

        return self._available

    def detect(self, text: str) -> list[PiiMatch]:
        if not self._ensure_analyzer():
            # Fallback to regex
            return RegexPiiDetector().detect(text)

        results = self._analyzer.analyze(
            text=text,
            entities=self._entities,
            language="en",
            score_threshold=self._score_threshold,
        )

        return [
            PiiMatch(
                entity_type=r.entity_type.lower(),
                text=text[r.start:r.end],
                start=r.start,
                end=r.end,
                score=r.score,
            )
            for r in results
        ]


def create_detector(
    backend: str = "regex",
    custom_patterns: dict[str, str] | None = None,
    presidio_score_threshold: float = 0.5,
    presidio_entities: list[str] | None = None,
) -> PiiDetector:
    """Factory: create a PII detector based on config."""
    if backend == "presidio":
        return PresidioPiiDetector(
            score_threshold=presidio_score_threshold,
            entities=presidio_entities,
        )
    return RegexPiiDetector(custom_patterns=custom_patterns)
