import re
from dataclasses import dataclass

_FENCE_RE = re.compile(r"```(markdown|html)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class Artifact:
    type: str  # "markdown" | "html"
    title: str | None
    content: str


def detect_artifact(text: str) -> Artifact | None:
    """Pull the first fenced ```markdown or ```html block out of a model response.

    Only the first match is used: a reply should produce at most one artifact
    per turn, keeping the artifact/message relationship one-to-one and the
    viewer state unambiguous.
    """
    match = _FENCE_RE.search(text)
    if not match:
        return None

    fence_type = match.group(1).lower()
    content = match.group(2).strip()
    if not content:
        return None

    title = _guess_title(content, fence_type)
    return Artifact(type=fence_type, title=title, content=content)


def _guess_title(content: str, fence_type: str) -> str | None:
    if fence_type == "markdown":
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
    else:
        title_match = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
        if title_match:
            return title_match.group(1).strip()
    return None


def strip_artifact_fence(text: str) -> str:
    """Replace the first fenced ```markdown/html block with a short pointer to
    the artifact panel, keeping any surrounding prose the model wrote outside
    the fence. Used for the chat-bubble display text so the raw fenced source
    doesn't render twice — once (unrendered) in the bubble, once (rendered) in
    the artifact panel.
    """
    match = _FENCE_RE.search(text)
    if not match:
        return text

    fence_type = match.group(1).lower()
    if not match.group(2).strip():
        return text

    label = "document" if fence_type == "markdown" else "HTML snippet"
    placeholder = f"_Opened as a {label} in the panel →_"
    before = text[: match.start()].strip()
    after = text[match.end() :].strip()
    return "\n\n".join(p for p in (before, placeholder, after) if p)
