"""Text, number and date normalisation shared by the linter, grader and verifier.

Everything here is deterministic and standard-library only, so grading never depends on a model.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import List, Optional

_ARTICLES = frozenset({"a", "an", "the"})


def strip_accents(text: str) -> str:
    """'Brasília' -> 'Brasilia', 'ị' -> 'i'. Decomposes, then drops combining marks."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def tokens(text: str, keep_accents: bool = False) -> List[str]:
    """Lower-cased word tokens with punctuation and articles removed."""
    text = unicodedata.normalize("NFKC", text).casefold()
    if not keep_accents:
        text = strip_accents(text)
    text = text.replace("’", "'").replace("'", "")
    text = re.sub(r"[^\w\s]", " ", text)
    return [t for t in text.split() if t not in _ARTICLES]


def contains_phrase(haystack: List[str], needle: List[str]) -> bool:
    """True if `needle` occurs as a contiguous run of tokens inside `haystack`."""
    if not needle:
        return False
    return (" " + " ".join(needle) + " ") in (" " + " ".join(haystack) + " ")


# ---------------------------------------------------------------- numbers

_NUMBER = re.compile(r"(?<![\w.])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])-?\d+(?:\.\d+)?")
_WHOLE_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")


def parse_number(text: str) -> Optional[float]:
    """Parse a string that *is* a number: '1,000', '$5', '92', '3.5%'. None otherwise."""
    cleaned = text.strip().strip("$€£").rstrip("%").replace(",", "").strip()
    return float(cleaned) if _WHOLE_NUMBER.fullmatch(cleaned) else None


def extract_numbers(text: str) -> List[float]:
    return [float(m.replace(",", "")) for m in _NUMBER.findall(text)]


# ------------------------------------------------------------------ dates

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MDY = re.compile(rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)
_DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_RE})\.?,?\s+(\d{{4}})\b", re.I)
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _iso(y: int, m: int, d: int) -> Optional[str]:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def extract_dates(text: str) -> List[str]:
    """All unambiguous dates in `text` as ISO strings. Numeric 03/04/2020 is deliberately NOT
    parsed: it is ambiguous (day-first or month-first), and guessing would corrupt grading."""
    found = set()
    for y, m, d in _ISO.findall(text):
        iso = _iso(int(y), int(m), int(d))
        if iso:
            found.add(iso)
    for mon, d, y in _MDY.findall(text):
        iso = _iso(int(y), _MONTHS[mon.lower()], int(d))
        if iso:
            found.add(iso)
    for d, mon, y in _DMY.findall(text):
        iso = _iso(int(y), _MONTHS[mon.lower()], int(d))
        if iso:
            found.add(iso)
    return sorted(found)


def parse_date(text: str) -> Optional[str]:
    """Parse a string that *is* a single date ('1969-07-20', 'July 20, 1969'). ISO or None."""
    text = text.strip()
    dates = extract_dates(text)
    if len(dates) != 1:
        return None
    for pattern in (_ISO, _MDY, _DMY):
        match = pattern.fullmatch(text)
        if match:
            return dates[0]
    return None


def is_valid_iso_date(text: str) -> bool:
    return bool(ISO_DATE.fullmatch(text.strip())) and bool(extract_dates(text.strip()))
