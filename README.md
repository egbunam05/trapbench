# trapbench

**Author, lint, grade and verify "hard to find, easy to verify" benchmark tasks for LLM evaluation.**

Benchmarks like GAIA, BrowseComp and SimpleQA rely on questions that need several research hops to *find* but that have one short answer anyone can *check*. Writing those questions well is mostly discipline: no leaked answers, no ambiguity, no time-sensitive wording, primary sources with exact quotes, and a grader that never argues with itself. `trapbench` turns that discipline into a command-line tool.

- **`lint`**: 25 rules catch authoring mistakes before a task reaches a model (offline).
- **`grade`**: deterministic grading with correct / incorrect / not-attempted verdicts. No model in the loop, so the same answers always get the same grade.
- **`verify`**: fetches every cited page and confirms your quote is actually on it.
- Pure Python standard library. Installs anywhere Python runs, including Termux.

```text
$ trapbench lint examples/bad_tasks.jsonl
line 2 [bad-leak] E004 error: task has no sources
line 2 [bad-leak] E005 error: the answer appears in the question
line 3 [bad-search] E010 error: https://www.google.com/search?q=... is a search page, not a source
line 4 [bad-quote] E008 error: none of the source quotes states the answer (or an alias)
line 5 [bad-date] E007 error: answer '20/07/1969' is not a valid yyyy-mm-dd date
line 7 [bad-wiki] W103 warn: en.wikipedia.org is secondary/user-generated: cite the underlying primary source
...
7 task(s): 6 error(s), 9 warning(s)
```

## Quickstart

```bash
git clone https://github.com/egbunam05/trapbench && cd trapbench
pip install -e ".[dev]"
pytest                                   # 110 tests, offline

trapbench init tasks.jsonl               # starter file
trapbench lint examples/tasks.jsonl --strict
trapbench grade examples/tasks.jsonl examples/answers.jsonl --details
trapbench verify tasks.jsonl             # needs network; checks quotes on the live pages
trapbench rules                          # list every rule
```

## The task format

One JSON object per line:

```json
{
  "id": "herschel-element",
  "question": "What is the atomic number of the chemical element named after the planet that William Herschel discovered in 1781?",
  "answer": "92",
  "answer_type": "number",
  "aliases": [],
  "sources": [
    {"url": "https://example.org/herschel-uranus", "quote": "Uranus was discovered by William Herschel in 1781."},
    {"url": "https://example.org/uranium", "quote": "Uranium is a chemical element with atomic number 92, named after the planet Uranus."}
  ],
  "steps": ["William Herschel discovered Uranus in 1781", "The element named after Uranus is uranium", "Uranium has atomic number 92"],
  "tags": ["science", "multi-hop"]
}
```

| Field | Meaning |
|---|---|
| `answer_type` | `string`, `number` (plain digits) or `date` (ISO `yyyy-mm-dd`). Typed answers compare by value, so `1,500` = `1500` and `July 20, 1969` = `1969-07-20`. |
| `aliases` | Other accepted answers (strings). Accent differences are already ignored, so you do not need them for `Brasilia` vs `Brasília`. |
| `sources[].quote` | The exact sentence on the page that supports the answer. At least one quote must state the answer. |
| `steps` | The reasoning hops a solver must make. Fewer than two suggests a single-search question. |
| `tolerance` | Optional absolute tolerance for number answers. |

> **About the example data:** the facts in `examples/` are real and unambiguous, but the source URLs are `example.org` placeholders so the files are safe to commit. `trapbench verify` against them will (correctly) fail. Use real primary-source URLs in your own tasks.

## Lint rules

Run `trapbench rules` for the full list. Errors fail the build; warnings fail it only with `--strict`; skip rules with `--ignore W102,W106`.

| Code | What it catches |
|---|---|
| E005 | The answer (or an alias) appears in the question |
| E008 | No source quote actually states the answer |
| E010 | A search-results page cited as a source |
| E004 / E009 | No sources / malformed URL |
| E006 / E007 | `number` answer isn't a number / `date` answer isn't ISO |
| W101 | Time-sensitive wording: "current", "latest", "this year" (the answer will drift) |
| W102 | Fewer than 2 reasoning steps (probably one search) |
| W103 | Wikipedia, Reddit, Quora, blogs as sources (cite the primary source) |
| W104 | "first", "largest", "only" without an explicit criterion |
| W105 / W107 | Compound questions / wording that invites several valid answers |
| W110 | Near-duplicate of another task (word overlap of 80% or more) |

## Grading

Verdicts follow the SimpleQA convention: **correct**, **incorrect**, or **not attempted** (the model declined). Declining is not penalised the way a wrong answer is, which is how you measure whether a model knows what it doesn't know. The report shows overall accuracy, accuracy given attempted, and their harmonic mean (F-score).

Two modes:

- `--mode lenient` (default): the answer may sit inside a short sentence. A response is marked **incorrect** if it is longer than `--max-words` (default 30), or if it names *other* numbers or dates alongside the right one. That closes the "list ten candidates and hope" loophole.
- `--mode strict`: the whole response must equal the answer after normalisation.

Normalisation ignores case, punctuation, articles and accents (`ọkụ` = `oku`; add `--keep-accents` when the diacritics carry meaning, as in Igbo). Numeric dates like `03/04/2020` are **never guessed**: they are ambiguous, so they never match.

Model answers come from any source as JSONL (`{"id": ..., "response": ...}`), so you can grade runs from any model or platform.

## Limitations

These matter if you plan to rely on the tool:

- **Lint is heuristic.** It catches common mistakes; it cannot tell whether a question is genuinely hard to search. That still takes a human and a real model run.
- **Lenient grading is lexical.** It will not accept a correct paraphrase that does not contain the answer text, and it cannot judge reasoning, only the final answer.
- **`verify` can false-flag.** JavaScript-rendered, paywalled or bot-blocking pages may not return the quoted text. Treat a V002 as "check by hand", not as proof the quote is wrong.
- **Number words are not parsed** ("ninety-two"). Use digits.
- The bundled example set is small and illustrative, not a benchmark.
- Tested on Python 3.13; CI runs 3.9, 3.11 and 3.13.

## Roadmap

- [ ] Optional LLM grader for paraphrased answers, with agreement reported against the deterministic grader
- [ ] `trapbench run`: query a model from the CLI and grade it in one step
- [ ] Per-tag breakdowns and a task-difficulty report across several models
- [ ] Inter-author review workflow (export tasks for a second person to audit)

## Layout

```text
src/trapbench/
  schema.py      task format + loaders
  normalize.py   text, number and date normalisation
  lint.py        25 rules, stable codes
  grade.py       deterministic grader and summary
  verify.py      live source + quote verification
  cli.py         lint / grade / verify / init / rules
examples/        a clean task set, a deliberately flawed one, sample answers
tests/           110 tests, all offline
```

## License

MIT
