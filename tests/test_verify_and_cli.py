import io
import json
import urllib.error
from pathlib import Path

import pytest

from trapbench import Task, TaskFileError, load_responses, load_tasks, verify_tasks
from trapbench.cli import main
from trapbench.verify import html_to_text

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples"


class FakeResponse:
    def __init__(self, body, status=200):
        self._body, self.status = body.encode(), status

    def read(self, n=-1):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_web(pages):
    """pages: url -> html string, int status, or an Exception."""
    seen = []

    def urlopen(request, timeout=None):
        url = request.full_url
        seen.append(url)
        page = pages[url]
        if isinstance(page, Exception):
            raise page
        if isinstance(page, int):
            raise urllib.error.HTTPError(url, page, "err", {}, io.BytesIO(b""))
        return FakeResponse(page)

    urlopen.seen = seen
    return urlopen


def one(url, quote="", answer="92", answer_type="number"):
    return Task.from_dict({"id": "t", "question": "q", "answer": answer, "answer_type": answer_type,
                           "sources": [{"url": url, "quote": quote}]}, line=1)


# ------------------------------------------------------------------ verify

def test_html_to_text_strips_scripts_tags_and_entities():
    html = "<html><script>var x = 'atomic number 99';</script><p>Uranium &amp; <b>atomic</b> number 92</p><!-- c --></html>"
    assert html_to_text(html) == "Uranium & atomic number 92"


def test_verify_passes_when_quote_is_on_the_page():
    web = fake_web({"https://a.example/u": "<p>Uranium has atomic number 92.</p>"})
    assert verify_tasks([one("https://a.example/u", "Uranium has atomic number 92.")], web, delay=0) == []


def test_verify_quote_matching_ignores_case_punctuation_and_markup():
    web = fake_web({"https://a.example/u": "<p>URANIUM has <i>atomic number</i> 92</p>"})
    assert verify_tasks([one("https://a.example/u", "Uranium has atomic number 92.")], web, delay=0) == []


def test_verify_flags_missing_quote_and_dead_links():
    web = fake_web({
        "https://a.example/changed": "<p>Something else entirely.</p>",
        "https://a.example/gone": 404,
        "https://a.example/down": urllib.error.URLError("timed out"),
    })
    tasks = [one("https://a.example/changed", "Uranium has atomic number 92."),
             one("https://a.example/gone", "x"), one("https://a.example/down", "x")]
    found = [(i.code, i.severity) for i in verify_tasks(tasks, web, delay=0)]
    assert found == [("V002", "error"), ("V001", "error"), ("V001", "error")]


def test_verify_without_quote_warns_if_answer_absent():
    web = fake_web({"https://a.example/u": "<p>Nothing relevant.</p>"})
    issues = verify_tasks([one("https://a.example/u")], web, delay=0)
    assert [i.code for i in issues] == ["V003"] and issues[0].severity == "warn"


def test_verify_fetches_each_url_once_and_is_polite():
    web = fake_web({"https://a.example/u": "<p>Uranium has atomic number 92.</p>",
                    "https://a.example/v": "<p>Uranium has atomic number 92.</p>"})
    sleeps = []
    tasks = [one("https://a.example/u", "atomic number 92"), one("https://a.example/u", "atomic number 92"),
             one("https://a.example/v", "atomic number 92")]
    verify_tasks(tasks, web, delay=2.5, sleep=sleeps.append)
    assert web.seen == ["https://a.example/u", "https://a.example/v"]
    assert sleeps == [2.5]  # no delay before the first request, none for the cached repeat


# ------------------------------------------------------------------- files

def test_load_tasks_reports_the_bad_line(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text('{"id": "a", "question": "q"}\n{broken\n')
    with pytest.raises(TaskFileError, match=r"t\.jsonl:2: invalid JSON"):
        load_tasks(f)


def test_load_tasks_rejects_non_objects_and_missing_files(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text("[1, 2]\n")
    with pytest.raises(TaskFileError, match="JSON object"):
        load_tasks(f)
    with pytest.raises(TaskFileError, match="cannot read"):
        load_tasks(tmp_path / "missing.jsonl")


def test_load_tasks_is_tolerant_of_loose_shapes(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text(json.dumps({"id": 7, "question": "q", "answer": 92, "aliases": "ninety-two",
                             "sources": "https://example.org/x"}) + "\n\n")
    (t,) = load_tasks(f)
    assert (t.id, t.answer, t.aliases, t.sources[0].url, t.line) == ("7", "92", ["ninety-two"], "https://example.org/x", 1)


def test_load_responses_accepts_alternate_keys(tmp_path):
    f = tmp_path / "a.jsonl"
    f.write_text('{"id": "a", "answer": "x"}\n{"id": "b", "output": "y"}\n')
    assert load_responses(f) == {"a": "x", "b": "y"}
    f.write_text('{"response": "x"}\n')
    with pytest.raises(TaskFileError, match="missing 'id'"):
        load_responses(f)


# --------------------------------------------------------------------- cli

def test_cli_lint_exit_codes(capsys):
    assert main(["lint", str(EX / "tasks.jsonl"), "--strict"]) == 0
    assert main(["lint", str(EX / "bad_tasks.jsonl")]) == 1
    assert "E005" in capsys.readouterr().out


def test_cli_strict_turns_warnings_into_failure(tmp_path):
    f = tmp_path / "t.jsonl"
    task = json.loads((EX / "tasks.jsonl").read_text().splitlines()[0])
    task["steps"] = []
    f.write_text(json.dumps(task) + "\n")
    assert main(["lint", str(f)]) == 0
    assert main(["lint", str(f), "--strict"]) == 1
    assert main(["lint", str(f), "--strict", "--ignore", "W102"]) == 0


def test_cli_lint_json(capsys):
    main(["lint", str(EX / "bad_tasks.jsonl"), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert {"task_id", "line", "code", "severity", "message"} <= set(data[0])


def test_cli_grade_example(capsys):
    assert main(["grade", str(EX / "tasks.jsonl"), str(EX / "answers.jsonl"), "--details"]) == 0
    out = capsys.readouterr().out
    counts = {line.split()[0] + (" " + line.split()[1] if line.split()[1] == "attempted" else ""): line.split()
              for line in out.splitlines() if line.strip().startswith(("correct", "incorrect", "not"))}
    assert counts["correct"][1] == "2" and counts["incorrect"][1] == "1" and counts["not attempted"][2] == "1"
    assert "(50% of all)" in out
    assert "FAIL rio-capital" in out and "skip curie-two-prizes" in out


def test_cli_grade_json_and_strict(capsys):
    main(["grade", str(EX / "tasks.jsonl"), str(EX / "answers.jsonl"), "--json", "--mode", "strict"])
    data = json.loads(capsys.readouterr().out)
    # strict: 'Uranium has atomic number 92.' is not a bare number
    assert data["summary"]["correct"] == 1 and len(data["grades"]) == 4


def test_cli_errors_are_clean(capsys):
    assert main(["lint", "nope.jsonl"]) == 2
    assert "error: cannot read nope.jsonl" in capsys.readouterr().err


def test_cli_init_refuses_to_overwrite(tmp_path, capsys):
    f = tmp_path / "tasks.jsonl"
    assert main(["init", str(f)]) == 0
    assert main(["init", str(f)]) == 1
    assert main(["init", str(f), "--force"]) == 0
    assert main(["lint", str(f)]) == 0  # the template itself is lint-clean


def test_cli_rules_lists_everything(capsys):
    assert main(["rules"]) == 0
    out = capsys.readouterr().out
    assert "E005" in out and "W110" in out and "V002" in out
