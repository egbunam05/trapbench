"""Static checks for benchmark tasks: every rule has a stable code so teams can ignore or enforce it.

These are heuristics. They catch the common authoring mistakes (answer leaked in the question,
unsupported answer key, time-sensitive wording, secondary sources). They cannot tell whether a
question is genuinely hard to search; that still needs a human and a real model run.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse

from .normalize import (
    contains_phrase,
    extract_dates,
    extract_numbers,
    is_valid_iso_date,
    parse_number,
    tokens,
)
from .schema import ANSWER_TYPES, Task

RULES: Dict[str, Tuple[str, str]] = {
    "E001": ("error", "question is empty"),
    "E002": ("error", "answer is empty"),
    "E003": ("error", "answer_type must be string, number or date"),
    "E004": ("error", "task has no sources"),
    "E005": ("error", "the answer appears in the question"),
    "E006": ("error", "number answer is not a plain number"),
    "E007": ("error", "date answer is not ISO yyyy-mm-dd"),
    "E008": ("error", "no source quote states the answer"),
    "E009": ("error", "source URL is not a valid http(s) URL"),
    "E010": ("error", "source is a search-engine results page"),
    "E011": ("error", "duplicate task id"),
    "E012": ("error", "task id is empty"),
    "W101": ("warn", "time-sensitive wording: the answer may change"),
    "W102": ("warn", "fewer than 2 reasoning steps: likely a single-search question"),
    "W103": ("warn", "secondary or user-generated source: prefer a primary source"),
    "W104": ("warn", "superlative or 'first/only' without an explicit criterion"),
    "W105": ("warn", "compound question: split it so there is one answer"),
    "W106": ("warn", "very short question: probably answerable with one search"),
    "W107": ("warn", "wording invites several valid answers"),
    "W108": ("warn", "long string answer: hard to grade unambiguously"),
    "W109": ("warn", "the same source URL is listed twice"),
    "W110": ("warn", "near-duplicate of another task"),
    "W111": ("warn", "an alias repeats the canonical answer"),
    "W112": ("warn", "answer looks like a number or date but answer_type is string"),
    "W115": ("warn", "a source has no quote: hard to audit"),
}

_TIME = re.compile(
    r"\b(current(?:ly)?|latest|recent(?:ly)?|now|today|nowadays|presently|newest|"
    r"this year|last year|next year|at present|as of now)\b",
    re.I,
)
_SUPERLATIVE = re.compile(
    r"\b(first|largest|smallest|biggest|oldest|youngest|tallest|longest|shortest|highest|"
    r"lowest|best|most|greatest|only)\b",
    re.I,
)
_MULTI = re.compile(
    r"\b(one of|any of|some of|list|name all|name any|which of the following|such as|for example|e\.g\.)\b",
    re.I,
)
_COMPOUND = re.compile(r"\band (?:also )?(?:what|which|who|when|where|how)\b", re.I)
_SECONDARY_HOSTS = (
    "wikipedia.org", "wikimedia.org", "reddit.com", "quora.com", "medium.com", "fandom.com",
    "blogspot.com", "wordpress.com", "answers.com", "wikihow.com", "facebook.com", "x.com",
    "twitter.com", "tiktok.com",
)
_SEARCH_HOSTS = ("google.com", "bing.com", "duckduckgo.com", "yahoo.com", "baidu.com", "yandex.com", "brave.com")


@dataclass
class Issue:
    task_id: str
    line: int
    code: str
    severity: str
    message: str

    def __str__(self) -> str:
        return f"line {self.line} [{self.task_id or '?'}] {self.code} {self.severity}: {self.message}"


def _parse_url(url: str):
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    return parsed


def _host_matches(host: str, suffixes: Iterable[str]) -> bool:
    host = host.lower()
    return any(host == s or host.endswith("." + s) for s in suffixes)


def _answer_in_text(task: Task, text: str) -> bool:
    """Does `text` state the answer (or an alias), compared in the answer's own type?"""
    if task.answer_type == "number":
        key = parse_number(task.answer)
        return key is not None and any(
            math.isclose(n, key, rel_tol=1e-9, abs_tol=max(task.tolerance, 1e-9)) for n in extract_numbers(text)
        )
    if task.answer_type == "date":
        return task.answer.strip() in extract_dates(text)
    haystack = tokens(text)
    return any(contains_phrase(haystack, tokens(c)) for c in task.candidates)


def lint_task(task: Task) -> List[Issue]:
    issues: List[Issue] = []

    def add(code: str, message: Optional[str] = None) -> None:
        severity, title = RULES[code]
        issues.append(Issue(task.id, task.line, code, severity, message or title))

    q = task.question
    if not task.id:
        add("E012")
    if not q:
        add("E001")
    if not task.answer:
        add("E002")
    if task.answer_type not in ANSWER_TYPES:
        add("E003", f"answer_type {task.answer_type!r} is not one of {', '.join(ANSWER_TYPES)}")

    if task.answer_type == "number" and task.answer and parse_number(task.answer) is None:
        add("E006", f"answer {task.answer!r} is not a plain number (write 1500, not '1.5 thousand')")
    if task.answer_type == "date" and task.answer and not is_valid_iso_date(task.answer):
        add("E007", f"answer {task.answer!r} is not a valid yyyy-mm-dd date")
    if task.answer_type == "string" and task.answer:
        if parse_number(task.answer) is not None:
            add("W112", "answer is numeric: set answer_type to 'number' so formats like 1,000 compare equal")
        elif len(extract_dates(task.answer)) == 1:
            add("W112", "answer is a date: set answer_type to 'date' and use yyyy-mm-dd")

    if q and task.answer:
        if task.answer_type == "string":
            leaked = any(contains_phrase(tokens(q), tokens(c)) for c in task.candidates if tokens(c))
        else:
            leaked = _answer_in_text(task, q)
        if leaked:
            add("E005")

    if q:
        if _TIME.search(q):
            add("W101", f"time-sensitive wording {_TIME.search(q).group(0)!r}: pin the question to a fixed date")
        if _SUPERLATIVE.search(q):
            add("W104", f"{_SUPERLATIVE.search(q).group(0)!r} needs an explicit criterion and a source that ranks")
        if q.count("?") > 1 or _COMPOUND.search(q):
            add("W105")
        if len(q.split()) < 8:
            add("W106")
        if _MULTI.search(q):
            add("W107", f"{_MULTI.search(q).group(0)!r} invites several valid answers")

    if len(task.steps) < 2:
        add("W102", f"{len(task.steps)} reasoning step(s) listed: multi-hop tasks should list at least 2")
    if task.answer_type == "string" and len(tokens(task.answer)) > 8:
        add("W108")
    canon = tokens(task.answer, keep_accents=True)  # accent variants are NOT repeats: see --keep-accents
    if any(tokens(a, keep_accents=True) == canon for a in task.aliases):
        add("W111")

    if not task.sources:
        add("E004")
    seen_urls: Set[str] = set()
    any_quote = missing_quote = False
    supported = False
    for source in task.sources:
        parsed = _parse_url(source.url)
        if parsed is None:
            add("E009", f"{source.url!r} is not a valid http(s) URL")
        else:
            host = parsed.hostname or ""
            if _host_matches(host, _SEARCH_HOSTS) and ("q=" in parsed.query or parsed.path.startswith("/search")):
                add("E010", f"{source.url} is a search page, not a source")
            elif _host_matches(host, _SECONDARY_HOSTS):
                add("W103", f"{host} is secondary/user-generated: cite the underlying primary source")
        key = source.url.strip().rstrip("/").lower()
        if key in seen_urls:
            add("W109", f"{source.url} is listed more than once")
        seen_urls.add(key)
        if source.quote:
            any_quote = True
            supported = supported or _answer_in_text(task, source.quote)
        else:
            missing_quote = True
    if any_quote and not supported and task.answer:
        add("E008", "none of the source quotes states the answer (or an alias)")
    if missing_quote and task.sources:
        add("W115")
    return issues


def _near_duplicates(tasks: List[Task], threshold: float = 0.8) -> List[Issue]:
    issues: List[Issue] = []
    sets = [set(tokens(t.question)) for t in tasks]
    for j in range(len(tasks)):
        for i in range(j):
            union = sets[i] | sets[j]
            if union and len(sets[i] & sets[j]) / len(union) >= threshold:
                severity, _ = RULES["W110"]
                issues.append(
                    Issue(tasks[j].id, tasks[j].line, "W110", severity, f"near-duplicate of task {tasks[i].id!r}")
                )
                break
    return issues


def lint(tasks: List[Task], ignore: Iterable[str] = ()) -> List[Issue]:
    ignored = {code.strip().upper() for code in ignore if code.strip()}
    issues: List[Issue] = []
    ids: Dict[str, int] = {}
    for task in tasks:
        issues.extend(lint_task(task))
        if task.id and task.id in ids:
            severity, _ = RULES["E011"]
            issues.append(Issue(task.id, task.line, "E011", severity, f"id also used on line {ids[task.id]}"))
        ids.setdefault(task.id, task.line)
    issues.extend(_near_duplicates(tasks))
    issues = [i for i in issues if i.code not in ignored]
    line_order = {t.line: n for n, t in enumerate(tasks)}
    issues.sort(key=lambda i: (line_order.get(i.line, 0), i.code))
    return issues
