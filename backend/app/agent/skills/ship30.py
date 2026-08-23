"""Ship 30 for 30 essay skill.

Encodes the principles from the assignment's own linked guide
(ship30for30.com/post/how-to-start-writing-online-the-ship-30-for-30-ultimate-guide)
as a structured prompt template plus a post-generation validator, rather than
a one-off "write an essay" prompt. The validator gives one automatic repair
pass so format drift (common with smaller local models) gets caught before
the essay reaches the user.
"""

import re
from dataclasses import dataclass, field

TARGET_WORDS = 1250
WORD_TOLERANCE = 250  # accept 1000-1500

SHIP30_SYSTEM_PROMPT = """You are writing a Ship 30 for 30 style essay grounded in Lenny's Podcast \
transcripts provided below as numbered sources. Follow this exact framework:

1. HEADLINE: answer WHO it's for (if niche), WHAT it's about, and WHY the reader should care. \
Use a curiosity gap — reveal the beginning and end of the idea, not the middle.
2. HOOK: open with one of: a story (end -> humble start -> promise of the middle), a framework \
you're about to teach, or an actionable-outcome tease. One to three sentences.
3. PROVEN APPROACH: pick exactly one organizing pattern — Steps, Lessons, or Mistakes — and use \
it consistently for every subheading. Do not mix patterns.
4. STRUCTURE: use "wheels & spokes" headings (## for major sections, ### for sub-points). Convert \
any list of 3+ items into actual bullets. Bold key phrases for skimmability. Alternate short \
punchy lines with longer explanatory ones (1/3/1 rhythm: one-line hook, a few lines of evidence, \
one-line landing).
5. RATE OF REVELATION: every sentence must add new information — never restate a prior sentence.
6. TAKEAWAY: close with a clearly labeled, specific, actionable takeaway the reader can apply today.
7. LENGTH: approximately {target_words} words.
8. GROUNDING: every non-obvious claim must cite a source tag like [S1] from the list below. If the \
sources don't support a strong claim, soften it or omit it — do not invent specifics.

Output the finished essay as a single fenced ```markdown code block, starting with a single \
top-level heading for the headline.

Sources:
{sources}
"""


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    issues: list[str] = field(default_factory=list)
    word_count: int = 0


def build_ship30_prompt(sources_block: str) -> str:
    return SHIP30_SYSTEM_PROMPT.format(target_words=TARGET_WORDS, sources=sources_block)


def _extract_essay_body(text: str) -> str:
    match = re.search(r"```markdown\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else text


def validate_ship30_draft(text: str) -> ValidationResult:
    body = _extract_essay_body(text)
    words = body.split()
    word_count = len(words)
    issues: list[str] = []

    if abs(word_count - TARGET_WORDS) > WORD_TOLERANCE:
        issues.append(f"word count {word_count} is outside the {TARGET_WORDS}±{WORD_TOLERANCE} target")

    headings = re.findall(r"^#{1,3}\s+.+$", body, re.MULTILINE)
    if len(headings) < 2:
        issues.append("fewer than 2 headings — structure isn't skimmable")

    if "**" not in body and "__" not in body:
        issues.append("no bolded phrases found")

    if not re.search(r"(takeaway|do this|start by|next time)", body, re.IGNORECASE):
        issues.append("no clearly labeled takeaway found")

    return ValidationResult(ok=not issues, issues=issues, word_count=word_count)


def build_repair_prompt(original_text: str, issues: list[str]) -> str:
    issue_list = "\n".join(f"- {i}" for i in issues)
    return (
        "Your previous Ship 30 for 30 draft below has formatting issues. Revise it to fix "
        f"ALL of the following, then output the corrected essay in the same ```markdown fenced "
        f"block format:\n{issue_list}\n\nPrevious draft:\n{original_text}"
    )
