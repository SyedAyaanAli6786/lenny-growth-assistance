from app.agent.skills.ship30 import TARGET_WORDS, build_repair_prompt, validate_ship30_draft


def _essay(word_count: int, with_bold: bool = True, with_headings: bool = True, with_takeaway: bool = True) -> str:
    body_words = " ".join(f"word{i}" for i in range(word_count))
    heading = "## Lesson 1: Something\n### A sub point\n" if with_headings else ""
    bold = "**key phrase**\n" if with_bold else ""
    takeaway = "\n\nTakeaway: start by doing the thing." if with_takeaway else ""
    return f"```markdown\n# Headline\n{heading}{bold}{body_words}{takeaway}\n```"


def test_valid_essay_passes():
    result = validate_ship30_draft(_essay(TARGET_WORDS))
    assert result.ok
    assert result.issues == []


def test_too_short_essay_fails_word_count():
    result = validate_ship30_draft(_essay(200))
    assert not result.ok
    assert any("word count" in issue for issue in result.issues)


def test_missing_headings_fails():
    result = validate_ship30_draft(_essay(TARGET_WORDS, with_headings=False))
    assert not result.ok
    assert any("heading" in issue for issue in result.issues)


def test_missing_bold_fails():
    result = validate_ship30_draft(_essay(TARGET_WORDS, with_bold=False))
    assert not result.ok
    assert any("bold" in issue for issue in result.issues)


def test_missing_takeaway_fails():
    result = validate_ship30_draft(_essay(TARGET_WORDS, with_takeaway=False))
    assert not result.ok
    assert any("takeaway" in issue for issue in result.issues)


def test_build_repair_prompt_includes_issues_and_original_text():
    original = "some draft text"
    prompt = build_repair_prompt(original, ["word count too low", "no bolded phrases found"])
    assert "word count too low" in prompt
    assert "no bolded phrases found" in prompt
    assert original in prompt
