from app.artifacts.detect import detect_artifact


def test_no_fenced_block_returns_none():
    assert detect_artifact("Just a plain text answer with no code block.") is None


def test_detects_markdown_artifact_and_title_from_heading():
    text = 'Sure, here you go:\n\n```markdown\n# My Great Doc\n\nSome content here.\n```\n\nHope that helps!'
    artifact = detect_artifact(text)
    assert artifact is not None
    assert artifact.type == "markdown"
    assert artifact.title == "My Great Doc"
    assert "Some content here." in artifact.content


def test_detects_html_artifact_and_title_from_title_tag():
    text = "```html\n<html><head><title>Landing Page</title></head><body>Hi</body></html>\n```"
    artifact = detect_artifact(text)
    assert artifact is not None
    assert artifact.type == "html"
    assert artifact.title == "Landing Page"


def test_empty_fenced_block_returns_none():
    assert detect_artifact("```markdown\n\n```") is None


def test_only_first_block_is_used_when_multiple_present():
    text = "```markdown\n# First\ncontent one\n```\n\nand also\n\n```html\n<p>second</p>\n```"
    artifact = detect_artifact(text)
    assert artifact.type == "markdown"
    assert artifact.title == "First"


def test_non_fenced_language_is_ignored():
    assert detect_artifact("```python\nprint('hi')\n```") is None
