import pytest

from trapbench.normalize import (
    contains_phrase,
    extract_dates,
    extract_numbers,
    is_valid_iso_date,
    parse_date,
    parse_number,
    strip_accents,
    tokens,
)


def test_accents_are_folded_including_igbo_marks():
    assert strip_accents("Brasília") == "Brasilia"
    assert strip_accents("ịgbọ ụlọ") == "igbo ulo"
    assert tokens("Brasília") == tokens("brasilia")


def test_keep_accents_distinguishes_letters():
    assert tokens("ọkụ", keep_accents=True) != tokens("oku", keep_accents=True)


def test_tokens_drop_articles_punctuation_and_case():
    assert tokens("The Nobel Prize, in Physics!") == ["nobel", "prize", "in", "physics"]
    assert tokens("Curie's lab") == tokens("Curies lab")


def test_contains_phrase_needs_whole_contiguous_words():
    hay = tokens("the capital is Brasilia today")
    assert contains_phrase(hay, ["brasilia"])
    assert not contains_phrase(tokens("Brasiliaville"), ["brasilia"])
    assert not contains_phrase(tokens("capital Brasilia"), ["brasilia", "capital"])
    assert not contains_phrase(hay, [])


@pytest.mark.parametrize(
    "text,value",
    [("92", 92.0), ("1,000", 1000.0), ("$5", 5.0), ("3.5%", 3.5), (" 42 ", 42.0), ("-7", -7.0)],
)
def test_parse_number(text, value):
    assert parse_number(text) == value


@pytest.mark.parametrize("text", ["", "ninety two", "92 atoms", "1.2.3", "abc"])
def test_parse_number_rejects_non_numbers(text):
    assert parse_number(text) is None


def test_extract_numbers_handles_commas_and_dates():
    assert extract_numbers("It cost 1,500 dollars in 1999") == [1500.0, 1999.0]
    assert extract_numbers("on 1969-07-20") == [1969.0, 7.0, 20.0]
    assert extract_numbers("none here") == []


@pytest.mark.parametrize(
    "text",
    ["1969-07-20", "July 20, 1969", "20 July 1969", "20th of July, 1969", "Jul 20 1969", "20 jul. 1969"],
)
def test_parse_date_formats_all_give_the_same_iso_date(text):
    assert parse_date(text) == "1969-07-20"


@pytest.mark.parametrize("text", ["20/07/1969", "07/20/1969", "July 1969", "1969", "February 30, 2020", ""])
def test_ambiguous_or_invalid_dates_are_not_guessed(text):
    assert parse_date(text) is None


def test_extract_dates_finds_several_in_a_sentence():
    text = "Launched 16 July 1969, landed July 20, 1969, returned 1969-07-24."
    assert extract_dates(text) == ["1969-07-16", "1969-07-20", "1969-07-24"]


def test_iso_date_validation():
    assert is_valid_iso_date("1969-07-20")
    assert not is_valid_iso_date("1969-13-20")
    assert not is_valid_iso_date("20/07/1969")
