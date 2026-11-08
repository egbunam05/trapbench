import pytest

from trapbench import CORRECT, INCORRECT, NOT_ATTEMPTED, Task, grade, grade_all, summarize


def task(answer, answer_type="string", **kw):
    return Task.from_dict({"id": "t", "question": "q", "answer": answer, "answer_type": answer_type, **kw})


def verdict(t, response, **kw):
    return grade(t, response, **kw).verdict


# ---------------------------------------------------------------- strings

def test_string_lenient_finds_answer_in_a_sentence():
    assert verdict(task("Marie Curie"), "It was Marie Curie, I believe.") == CORRECT


def test_string_strict_needs_the_whole_response():
    t = task("Marie Curie")
    assert verdict(t, "Marie Curie", mode="strict") == CORRECT
    assert verdict(t, "marie curie.", mode="strict") == CORRECT
    assert verdict(t, "It was Marie Curie", mode="strict") == INCORRECT


def test_aliases_and_accents():
    t = task("Brasília", aliases=["Federal Capital of Brazil"])
    assert verdict(t, "Brasilia") == CORRECT  # accent folded
    assert verdict(t, "Federal Capital of Brazil") == CORRECT  # alias
    assert verdict(t, "Brasilia", keep_accents=True) == INCORRECT  # exact accents demanded


def test_igbo_diacritics_fold_by_default():
    t = task("ọkụ")
    assert verdict(t, "oku") == CORRECT
    assert verdict(t, "oku", keep_accents=True) == INCORRECT


def test_partial_word_does_not_count():
    assert verdict(task("Rome"), "Romeo and Juliet") == INCORRECT


def test_wrong_answer_is_incorrect():
    assert verdict(task("Brasília"), "Rio de Janeiro") == INCORRECT


def test_spray_and_pray_long_response_is_incorrect():
    long = "Maybe " + " or ".join(f"city{i}" for i in range(20)) + " or Marie Curie"
    g = grade(task("Marie Curie"), long, max_words=30)
    assert g.verdict == INCORRECT and "words" in g.reason
    assert verdict(task("Marie Curie"), long, max_words=100) == CORRECT


# ------------------------------------------------------------ abstentions

@pytest.mark.parametrize("text", ["I don't know.", "I'm not sure", "I couldn't find that", "I can’t determine this"])
def test_abstentions_are_not_attempted(text):
    assert verdict(task("Marie Curie"), text) == NOT_ATTEMPTED


def test_empty_response_is_not_attempted():
    assert verdict(task("x"), "") == NOT_ATTEMPTED
    assert verdict(task("x"), None) == NOT_ATTEMPTED
    assert verdict(task("x"), "   ") == NOT_ATTEMPTED


def test_hedged_but_correct_still_counts_as_correct():
    assert verdict(task("Marie Curie"), "I'm not sure, but I think Marie Curie") == CORRECT


# ---------------------------------------------------------------- numbers

def test_number_lenient_in_sentence_and_with_commas():
    assert verdict(task("92", "number"), "Uranium has atomic number 92.") == CORRECT
    assert verdict(task("1500", "number"), "About 1,500 seats") == CORRECT


def test_number_conflicting_numbers_are_ambiguous():
    g = grade(task("92", "number"), "Discovered in 1781, atomic number 92")
    assert g.verdict == INCORRECT and "other numbers" in g.reason


def test_number_strict_requires_a_bare_number():
    t = task("92", "number")
    assert verdict(t, "92", mode="strict") == CORRECT
    assert verdict(t, "$92", mode="strict") == CORRECT
    assert verdict(t, "It is 92", mode="strict") == INCORRECT


def test_number_wrong_and_missing():
    t = task("92", "number")
    assert verdict(t, "It is 93") == INCORRECT
    assert verdict(t, "Uranium") == INCORRECT
    assert verdict(t, "I don't know") == NOT_ATTEMPTED


def test_number_tolerance():
    t = task("100", "number", tolerance=0.5)
    assert verdict(t, "100.4") == CORRECT
    assert verdict(t, "101") == INCORRECT


# ------------------------------------------------------------------ dates

def test_date_formats_are_equivalent():
    t = task("1969-07-20", "date")
    for text in ("July 20, 1969", "20 July 1969", "1969-07-20", "It landed on the 20th of July, 1969."):
        assert verdict(t, text) == CORRECT, text


def test_date_wrong_or_ambiguous():
    t = task("1969-07-20", "date")
    assert verdict(t, "July 21, 1969") == INCORRECT
    assert verdict(t, "20/07/1969") == INCORRECT  # numeric dates are never guessed
    assert grade(t, "Launched July 16, 1969 and landed July 20, 1969").verdict == INCORRECT
    assert verdict(t, "I don't know") == NOT_ATTEMPTED


def test_date_strict():
    t = task("1969-07-20", "date")
    assert verdict(t, "July 20, 1969", mode="strict") == CORRECT
    assert verdict(t, "It was July 20, 1969", mode="strict") == INCORRECT


def test_unparseable_number_key_falls_back_to_string_grading():
    assert verdict(task("about ninety", "number"), "about ninety") == CORRECT


def test_bad_mode_raises():
    with pytest.raises(ValueError):
        grade(task("x"), "x", mode="fuzzy")


# --------------------------------------------------------------- summaries

def test_grade_all_and_summary_numbers():
    tasks = [Task.from_dict({"id": f"t{i}", "question": "q", "answer": "yes"}) for i in range(4)]
    responses = {"t0": "yes", "t1": "no", "t2": "I don't know", "ghost": "yes"}
    grades, unknown = grade_all(tasks, responses)
    assert [g.verdict for g in grades] == [CORRECT, INCORRECT, NOT_ATTEMPTED, NOT_ATTEMPTED]
    assert grades[3].reason == "no response supplied"
    assert unknown == ["ghost"]
    s = summarize(grades)
    assert (s["n"], s["correct"], s["incorrect"], s["not_attempted"]) == (4, 1, 1, 2)
    assert s["accuracy"] == 0.25 and s["accuracy_given_attempted"] == 0.5
    assert s["f_score"] == pytest.approx(2 * 0.25 * 0.5 / 0.75)


def test_summary_of_nothing_does_not_divide_by_zero():
    assert summarize([])["f_score"] == 0.0
    only_skips = summarize(grade_all([Task.from_dict({"id": "a", "answer": "x"})], {})[0])
    assert only_skips["accuracy_given_attempted"] == 0.0
