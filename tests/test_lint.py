from pathlib import Path

import pytest

from trapbench import Task, lint, lint_task, load_tasks
from trapbench.lint import RULES

ROOT = Path(__file__).resolve().parent.parent


def make(**overrides):
    """A clean task; each test breaks exactly one thing."""
    base = {
        "id": "t1",
        "question": "What is the atomic number of the element named after the planet found by Herschel in 1781?",
        "answer": "92",
        "answer_type": "number",
        "sources": [{"url": "https://example.org/uranium", "quote": "Uranium has atomic number 92."}],
        "steps": ["Herschel found Uranus", "The element is uranium"],
    }
    base.update(overrides)
    return Task.from_dict(base, line=1)


def codes(task):
    return {i.code for i in lint_task(task)}


def test_clean_task_has_no_issues():
    assert lint_task(make()) == []


def test_every_rule_has_a_valid_severity():
    assert all(sev in ("error", "warn") for sev, _ in RULES.values())
    assert all(code[0] == ("E" if RULES[code][0] == "error" else "W") for code in RULES)


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"question": ""}, "E001"),
        ({"answer": ""}, "E002"),
        ({"answer_type": "list"}, "E003"),
        ({"sources": []}, "E004"),
        ({"answer": "ninety two"}, "E006"),
        ({"answer_type": "date", "answer": "20/07/1969"}, "E007"),
        ({"id": ""}, "E012"),
    ],
)
def test_error_rules(overrides, code):
    assert code in codes(make(**overrides))


def test_answer_leaked_in_question_string_number_and_alias():
    assert "E005" in codes(make(answer_type="string", answer="Herschel", question="Which Herschel found Uranus?"))
    assert "E005" in codes(make(question="Is the element with atomic number 92 named after Uranus really?"))
    assert "E005" in codes(
        make(answer_type="string", answer="Marie Curie", aliases=["Curie"], question="Which scientist named Curie won two prizes?")
    )


def test_date_answer_leak():
    task = make(answer_type="date", answer="1969-07-20", question="What happened on July 20, 1969 on the Moon today?")
    assert "E005" in codes(task)


def test_quote_must_state_the_answer_somewhere():
    assert "E008" in codes(make(sources=[{"url": "https://example.org/a", "quote": "Uranium is a metal."}]))


def test_multi_hop_only_needs_one_quote_to_state_the_answer():
    sources = [
        {"url": "https://example.org/a", "quote": "Herschel discovered Uranus in 1781."},
        {"url": "https://example.org/b", "quote": "Uranium has atomic number 92."},
    ]
    assert "E008" not in codes(make(sources=sources))


def test_quote_matching_respects_answer_type():
    # '1,500' in the quote must satisfy the number 1500; a date written out must satisfy the ISO key.
    assert "E008" not in codes(make(answer="1500", sources=[{"url": "https://example.org/a", "quote": "It has 1,500 seats."}]))
    date_task = make(answer_type="date", answer="1969-07-20", sources=[{"url": "https://example.org/a", "quote": "Landed 20 July 1969."}])
    assert "E008" not in codes(date_task)


@pytest.mark.parametrize("url", ["not a url", "ftp://example.org/x", "https://", ""])
def test_invalid_urls(url):
    assert "E009" in codes(make(sources=[{"url": url, "quote": "Uranium has atomic number 92."}]))


def test_search_engine_pages_are_not_sources():
    url = "https://www.google.com/search?q=uranium"
    assert "E010" in codes(make(sources=[{"url": url, "quote": "Uranium has atomic number 92."}]))
    assert "E010" not in codes(make(sources=[{"url": "https://www.google.com/about", "quote": "Uranium has atomic number 92."}]))


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"question": "Who is the current head of the agency that employed the engineer that built it all?"}, "W101"),
        ({"steps": ["only one"]}, "W102"),
        ({"sources": [{"url": "https://en.wikipedia.org/wiki/Uranium", "quote": "Uranium has atomic number 92."}]}, "W103"),
        ({"question": "What is the atomic number of the largest element named after a planet found by Herschel?"}, "W104"),
        ({"question": "What is the atomic number of the element named after a planet and what year was it found?"}, "W105"),
        ({"question": "What is uranium's atomic number?"}, "W106"),
        ({"question": "Name one of the elements that was named after a planet discovered during the 1700s?"}, "W107"),
        ({"answer_type": "string", "answer": "a very long answer that goes on and on for far too many words here"}, "W108"),
        ({"sources": [{"url": "https://example.org/a", "quote": "Uranium has atomic number 92."}] * 2}, "W109"),
        ({"answer_type": "string", "answer": "Marie Curie", "aliases": ["marie curie."]}, "W111"),
        ({"answer_type": "string"}, "W112"),
        ({"sources": [{"url": "https://example.org/a"}]}, "W115"),
    ],
)
def test_warning_rules(overrides, code):
    assert code in codes(make(**overrides))


def test_warnings_do_not_include_errors_for_a_merely_weak_task():
    issues = lint_task(make(steps=[]))
    assert {i.severity for i in issues} == {"warn"}


def test_accent_variants_are_not_flagged_as_duplicate_aliases():
    task = make(answer_type="string", answer="Brasília", aliases=["Brasilia"],
                sources=[{"url": "https://example.org/a", "quote": "The capital is Brasília."}],
                question="What is the capital city of the country that hosted the 2016 Summer Olympic Games?")
    assert "W111" not in codes(task)


def test_set_level_rules_duplicate_ids_and_near_duplicates():
    a = make(id="same")
    b = Task.from_dict({**{"id": "same", "question": a.question + " exactly", "answer": "92", "answer_type": "number",
                           "sources": [{"url": "https://example.org/u", "quote": "Uranium has atomic number 92."}],
                           "steps": ["a", "b"]}}, line=2)
    found = {i.code for i in lint([a, b])}
    assert {"E011", "W110"} <= found


def test_ignore_removes_rules():
    task = make(steps=[])
    assert any(i.code == "W102" for i in lint([task]))
    assert not any(i.code == "W102" for i in lint([task], ignore=["w102"]))


def test_clean_example_file_passes_strict():
    assert lint(load_tasks(ROOT / "examples" / "tasks.jsonl")) == []


def test_flawed_example_file_trips_every_intended_rule():
    found = {i.code for i in lint(load_tasks(ROOT / "examples" / "bad_tasks.jsonl"))}
    expected = {"E004", "E005", "E007", "E008", "E010", "W101", "W102", "W103", "W104", "W105", "W107", "W110", "W115"}
    assert expected <= found
