"""Online check: do the cited pages exist, and do they actually say what the answer key claims?

This is the 'easy to verify' half of 'hard to find, easy to verify'. It needs network access,
so it is separate from `lint` and always optional.
"""
from __future__ import annotations

import html
import re
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional, Tuple

from .lint import Issue
from .normalize import contains_phrase, tokens
from .schema import Task

USER_AGENT = "trapbench/0.1 (benchmark source verifier)"
MAX_BYTES = 2_000_000

VERIFY_RULES = {
    "V001": "error",  # page unreachable
    "V002": "error",  # quote not on page
    "V003": "warn",   # answer not on page (no quote given)
}

_SCRIPT = re.compile(r"<(script|style|noscript)\b.*?</\1>", re.I | re.S)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_TAG = re.compile(r"<[^>]+>")


def html_to_text(raw: str) -> str:
    raw = _COMMENT.sub(" ", _SCRIPT.sub(" ", raw))
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", raw))).strip()


def fetch(url: str, urlopen: Callable = urllib.request.urlopen, timeout: float = 15.0) -> Tuple[int, str]:
    """Return (status, text). Status 0 means the request itself failed (text holds the reason)."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"})
    try:
        with urlopen(request, timeout=timeout) as resp:
            body = resp.read(MAX_BYTES)
            headers = getattr(resp, "headers", None)
            charset = headers.get_content_charset() if hasattr(headers, "get_content_charset") else None
            return getattr(resp, "status", 200), html_to_text(body.decode(charset or "utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return 0, str(getattr(exc, "reason", exc))


def verify_tasks(tasks: List[Task], urlopen: Optional[Callable] = None, timeout: float = 15.0,
                 delay: float = 1.0, sleep: Callable[[float], None] = time.sleep) -> List[Issue]:
    opener = urlopen or urllib.request.urlopen
    cache: Dict[str, Tuple[int, str]] = {}
    issues: List[Issue] = []
    requests_made = 0
    for task in tasks:
        for source in task.sources:
            url = source.url.strip()
            if not url:
                continue
            if url not in cache:
                if requests_made and delay:
                    sleep(delay)  # be polite to the sites being checked
                cache[url] = fetch(url, opener, timeout)
                requests_made += 1
            status, page = cache[url]
            if status == 0 or status >= 400:
                why = page if status == 0 else f"HTTP {status}"
                issues.append(Issue(task.id, task.line, "V001", "error", f"{url} unreachable ({why})"))
                continue
            page_tokens = tokens(page)
            if source.quote:
                if not contains_phrase(page_tokens, tokens(source.quote)):
                    issues.append(Issue(task.id, task.line, "V002", "error",
                                        f"quote not found on {url} (page may be JS-rendered or the text changed)"))
            elif task.answer and not any(contains_phrase(page_tokens, tokens(c)) for c in task.candidates):
                issues.append(Issue(task.id, task.line, "V003", "warn",
                                    f"{url} does not contain the answer (add a quote so this can be checked exactly)"))
    return issues
