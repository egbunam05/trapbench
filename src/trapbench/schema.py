"""Task file format: one JSON object per line (JSONL).

A good task is *hard to find, easy to verify*: it needs several hops of research, but the answer
is short, unambiguous, and backed by quoted primary sources.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Union

ANSWER_TYPES = ("string", "number", "date")


class TaskFileError(ValueError):
    """The file could not be read as tasks (bad JSON, wrong shape)."""


@dataclass
class Source:
    url: str = ""
    quote: str = ""  # the exact sentence on the page that supports the answer
    note: str = ""


@dataclass
class Task:
    id: str = ""
    question: str = ""
    answer: str = ""  # canonical answer. Dates: ISO yyyy-mm-dd. Numbers: digits.
    answer_type: str = "string"  # string | number | date
    aliases: List[str] = field(default_factory=list)  # other accepted spellings (strings only)
    sources: List[Source] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)  # the reasoning hops a solver must make
    tags: List[str] = field(default_factory=list)
    tolerance: float = 0.0  # absolute tolerance for number answers
    line: int = 0  # 1-based line in the file, for error messages

    @classmethod
    def from_dict(cls, data: Dict[str, Any], line: int = 0) -> "Task":
        def text_list(value: Any) -> List[str]:
            if value is None:
                return []
            if isinstance(value, (str, int, float)):
                return [str(value)]
            return [str(v) for v in value]

        sources: List[Source] = []
        raw = data.get("sources") or []
        if isinstance(raw, (str, dict)):
            raw = [raw]
        for item in raw:
            if isinstance(item, str):
                sources.append(Source(url=item))
            elif isinstance(item, dict):
                sources.append(
                    Source(str(item.get("url") or ""), str(item.get("quote") or ""), str(item.get("note") or ""))
                )
        try:
            tolerance = float(data.get("tolerance") or 0.0)
        except (TypeError, ValueError):
            tolerance = 0.0
        answer = data.get("answer")
        return cls(
            id=str(data.get("id") or ""),
            question=str(data.get("question") or "").strip(),
            answer="" if answer is None else str(answer).strip(),
            answer_type=str(data.get("answer_type") or "string").strip().lower(),
            aliases=text_list(data.get("aliases")),
            sources=sources,
            steps=text_list(data.get("steps")),
            tags=text_list(data.get("tags")),
            tolerance=tolerance,
            line=line,
        )

    @property
    def candidates(self) -> List[str]:
        """The canonical answer plus every alias."""
        return [c for c in [self.answer, *self.aliases] if c]


def _read_jsonl(path: Union[str, Path]) -> Iterable[tuple]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise TaskFileError(f"cannot read {path}: {exc.strerror or exc}") from None
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TaskFileError(f"{path}:{number}: invalid JSON ({exc.msg})") from None
        if not isinstance(obj, dict):
            raise TaskFileError(f"{path}:{number}: each line must be a JSON object")
        yield number, obj


def load_tasks(path: Union[str, Path]) -> List[Task]:
    return [Task.from_dict(obj, line=n) for n, obj in _read_jsonl(path)]


def load_responses(path: Union[str, Path]) -> Dict[str, str]:
    """Model answers: JSONL of {"id": ..., "response": ...} ('answer' / 'output' / 'text' also work)."""
    out: Dict[str, str] = {}
    for number, obj in _read_jsonl(path):
        if "id" not in obj:
            raise TaskFileError(f"{path}:{number}: missing 'id'")
        value = next((obj[k] for k in ("response", "answer", "output", "text") if k in obj), None)
        if value is None:
            raise TaskFileError(f"{path}:{number}: missing 'response'")
        out[str(obj["id"])] = str(value)
    return out


TEMPLATE = (
    '{"id": "example-1", "question": "Replace me: a multi-hop question with one short, unambiguous answer?", '
    '"answer": "42", "answer_type": "number", "aliases": [], '
    '"sources": [{"url": "https://example.org/primary-source", "quote": "The exact sentence stating 42."}], '
    '"steps": ["First hop the solver must make", "Second hop that reaches the answer"], "tags": ["draft"]}\n'
)
