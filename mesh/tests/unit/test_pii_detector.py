"""Tests for pluggable PII detector backends."""

import pytest

from runtime.sidecar.interceptors.pii_detector import (
    PiiMatch,
    RegexPiiDetector,
    PresidioPiiDetector,
    create_detector,
)


class TestRegexPiiDetector:
    """Regression tests — regex detector must find all current pattern types."""

    def test_email(self):
        detector = RegexPiiDetector()
        matches = detector.detect("contact user@example.com for details")
        types = {m.entity_type for m in matches}
        assert "email" in types
        assert any(m.text == "user@example.com" for m in matches)

    def test_phone(self):
        detector = RegexPiiDetector()
        matches = detector.detect("call +1 (555) 123-4567")
        types = {m.entity_type for m in matches}
        assert "phone" in types

    def test_ssn(self):
        detector = RegexPiiDetector()
        matches = detector.detect("SSN: 123-45-6789")
        types = {m.entity_type for m in matches}
        assert "ssn" in types
        assert any(m.text == "123-45-6789" for m in matches)

    def test_credit_card(self):
        detector = RegexPiiDetector()
        matches = detector.detect("card: 4111 1111 1111 1111")
        types = {m.entity_type for m in matches}
        assert "credit_card" in types

    def test_ip_address(self):
        detector = RegexPiiDetector()
        matches = detector.detect("server at 192.168.1.100")
        types = {m.entity_type for m in matches}
        assert "ip_address" in types

    def test_uk_postcode(self):
        detector = RegexPiiDetector()
        matches = detector.detect("address: SW1A 2AA")
        types = {m.entity_type for m in matches}
        assert "uk_postcode" in types

    def test_no_pii(self):
        detector = RegexPiiDetector()
        matches = detector.detect("this is a clean message with no personal data")
        assert matches == []

    def test_custom_patterns(self):
        detector = RegexPiiDetector(custom_patterns={"emp_id": r"EMP-\d{6}"})
        matches = detector.detect("employee EMP-123456 requested access")
        types = {m.entity_type for m in matches}
        assert "emp_id" in types

    def test_match_positions(self):
        detector = RegexPiiDetector()
        text = "email: user@example.com done"
        matches = detector.detect(text)
        for m in matches:
            if m.entity_type == "email":
                assert text[m.start:m.end] == m.text
                assert m.text == "user@example.com"
                break


class TestPresidioPiiDetector:
    """Tests for the Presidio backend — graceful fallback if not installed."""

    def test_fallback_to_regex_when_not_installed(self):
        """If presidio_analyzer isn't installed, should fall back to regex."""
        detector = PresidioPiiDetector()
        matches = detector.detect("email: user@example.com")
        # Should still find the email via regex fallback
        types = {m.entity_type for m in matches}
        assert "email" in types

    def test_score_threshold(self):
        detector = PresidioPiiDetector(score_threshold=0.9)
        assert detector._score_threshold == 0.9


class TestCreateDetector:
    def test_creates_regex_by_default(self):
        detector = create_detector()
        assert isinstance(detector, RegexPiiDetector)

    def test_creates_regex_explicitly(self):
        detector = create_detector(backend="regex")
        assert isinstance(detector, RegexPiiDetector)

    def test_creates_presidio(self):
        detector = create_detector(backend="presidio")
        assert isinstance(detector, PresidioPiiDetector)

    def test_custom_patterns_passed_to_regex(self):
        detector = create_detector(
            backend="regex",
            custom_patterns={"test": r"TEST-\d+"},
        )
        matches = detector.detect("code TEST-42 here")
        types = {m.entity_type for m in matches}
        assert "test" in types
