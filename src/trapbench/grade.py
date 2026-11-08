"""Deterministic grading with SimpleQA-style verdicts: correct, incorrect, not attempted.

No model is involved, so the same answers always get the same grade. Two modes:

  strict   the whole response must equal the answer (after normalisation)
  lenient  the response may contain the answer inside a short sentence, but it is marked
           incorrect if it is long (spray-and-pray) or names *other* numbers/dates (hedging)
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .normalize import contains_phrase, extract_dates, extract_numbers, parse_date, parse_number, tokens
from .schema import Task

CORRECT, INCORRECT, NOT_ATTEMPTED = "correct", "incorrect", "not_attempted"

_ABSTAIN = re.compile(
    r"(i (?:do not|don't|dont) know|not sure|unsure|(?:cannot|can't|couldn't|could not|unable to) "
    r"(?:find|determine|answer|verify)|no (?:information|record)|insufficient (?:information|evidence))",
    re.I,
)


@dataclass
class Grade:
    id: str
    verdict: str
    reason: str
    response: str = ""


def _close(a: float, b: float, tolerance: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=max(tolerance, 1e-9))


def _verdict_for_missing(abstained: bool, reason: str) -> Tuple[str, str]:
    return (NOT_ATTEMPTED, "model declined to answer") if abstained else (INCORRECT, reason)


def grade(task: Task, response: Optional[str], mode: str = "lenient", max_words: int = 30,
          keep_accents: bool = False) -> Grade:
    if mode not in ("strict", "lenient"):
        raise ValueError("mode must be 'strict' or 'lenient'")
    text = (response or "").replace("’", "'").strip()
    if not text:
        return Grade(task.id, NOT_ATTEMPTED, "empty response", text)
    abstained = bool(_ABSTAIN.search(text))
    words = len(text.split())

    def done(verdict: str, reason: str) -> Grade:
        return Grade(task.id, verdict, reason, text)

    if task.answer_type == "number" and parse_number(task.answer) is not None:
        key = parse_number(task.answer)
        if mode == "strict":
            value = parse_number(text)
            if value is not None and _close(value, key, task.tolerance):
                return done(CORRECT, "exact number")
            return done(*_verdict_for_missing(abstained and value is None, f"expected {task.answer}"))
        numbers = sorted(set(extract_numbers(text)))
        hit = any(_close(n, key, task.tolerance) for n in numbers)
        if not hit:
            return done(*_verdict_for_missing(abstained, f"expected {task.answer}, found {numbers or 'no number'}"))
        if len(numbers) > 1:
            return done(INCORRECT, f"response also contains other numbers {numbers}: ambiguous")
        if words > max_words:
            return done(INCORRECT, f"response is {words} words (limit {max_words})")
        return done(CORRECT, "number found")

    if task.answer_type == "date":
        if mode == "strict":
            value = parse_date(text)
            if value == task.answer:
                return done(CORRECT, "exact date")
            return done(*_verdict_for_missing(abstained and value is None, f"expected {task.answer}"))
        dates = extract_dates(text)
        if task.answer not in dates:
            return done(*_verdict_for_missing(abstained, f"expected {task.answer}, found {dates or 'no date'}"))
        if len(dates) > 1:
            return done(INCORRECT, f"response also contains other dates {dates}: ambiguous")
        if words > max_words:
            return done(INCORRECT, f"response is {words} words (limit {max_words})")
        return done(CORRECT, "date found")

    response_tokens = tokens(text, keep_accents)
    candidates = [tokens(c, keep_accents) for c in task.candidates]
    if mode == "strict":
        if any(response_tokens == c for c in candidates if c):
            return done(CORRECT, "exact match")
        return done(*_verdict_for_missing(abstained, "does not match the answer or any alias"))
    if any(contains_phrase(response_tokens, c) for c in candidates):
        if words > max_words:
            return done(INCORRECT, f"response is {words} words (limit {max_words})")
        return done(CORRECT, "answer found")
    return done(*_verdict_for_missing(abstained, "answer not found in response"))


def grade_all(tasks: List[Task], responses: Dict[str, str], mode: str = "lenient", max_words: int = 30,
              keep_accents: bool = False) -> Tuple[List[Grade], List[str]]:
    """Grade every task. A task with no response counts as not attempted.
    Returns (grades, ids that had a response but no matching task)."""
    grades = []
    for task in tasks:
        if task.id in responses:
            grades.append(grade(task, responses[task.id], mode, max_words, keep_accents))
        else:
            grades.append(Grade(task.id, NOT_ATTEMPTED, "no response supplied"))
    known = {t.id for t in tasks}
    return grades, sorted(set(responses) - known)


def summarize(grades: List[Grade]) -> Dict[str, Optional[float]]:
    n = len(grades)
    correct = sum(g.verdict == CORRECT for g in grades)
    incorrect = sum(g.verdict == INCORRECT for g in grades)
    skipped = n - correct - incorrect
    attempted = correct + incorrect
    overall = correct / n if n else 0.0
    given_attempted = correct / attempted if attempted else 0.0
    f_score = (2 * overall * given_attempted / (overall + given_attempted)) if (overall + given_attempted) else 0.0
    return {
        "n": n,
        "correct": correct,
        "incorrect": incorrect,
        "not_attempted": skipped,
        "accuracy": overall,
        "accuracy_given_attempted": given_attempted,
        "f_score": f_score,
    }
