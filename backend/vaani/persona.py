"""What the model is sent: the input guardrail, then prompt assembly.

The two live together because their ORDER is the point. A transcript is
untrusted text: a person can say "ignore your instructions" into the
microphone. While it is still a separate string we can check it. Once it has
been placed in the request beside the system prompt, it is just more text and
there is no longer any way to tell instruction from content. So reply.py
calls `looks_like_injection` first and `assemble` only if that passed.

Persona prompts themselves are strings in config.toml's [personas] table,
looked up by key; nothing persona-specific is written here. Added to them
on every turn: the current date and time ([llm].timezone), and after it, in
a session that forces a reply language (protocol v0.10), one line naming it.
"""

import re
from datetime import datetime

from vaani.providers.base import Message


def looks_like_injection(transcript: str, patterns: list[str]) -> bool:
    """True if any guardrail pattern matches the transcript.

    `re` keeps its own cache of compiled patterns, so compiling on every call
    costs nothing after the first turn. The patterns were already checked to
    compile when config loaded.
    """
    return any(re.search(p, transcript, re.IGNORECASE) for p in patterns)


def clock_line(now: datetime) -> str:
    """The date and time line, e.g. "Current date and time (Asia/Kolkata):
    Tuesday, 14 October 2026, 14:05." `now` carries its zone (ZoneInfo).

    The model has no clock: without this line it invents a date. Weekday and
    month names come from strftime, which is English under Python's default
    "C" locale (nothing in the server changes the locale).
    """
    return (
        f"Current date and time ({now.tzinfo}): "
        f"{now:%A}, {now.day} {now:%B %Y}, {now:%H:%M}."
    )


# session.start's reply_language -> the line that ends the system prompt.
# "any" has no line: the reply follows the user's language (the prompt's own
# rule). Each persona prompt says a "Reply language" line overrides that rule.
# The script is named as well as the language: "Hindi" alone lets a model
# write romanized Hindi, which the Hindi voice cannot read.
REPLY_LANGUAGE_LINES = {
    "en": "Reply language: English (Latin script).",
    "hi": "Reply language: Hindi (Devanagari script).",
}


def assemble(
    system_prompt: str,
    history: list[Message],
    transcript: str,
    now: datetime,
    reply_language: str,  # "any", "en" or "hi": the session's, from session.start
) -> list[Message]:
    """The full request: persona system prompt, past exchanges, this turn.

    `history` is already capped (Session.remember trims it), so this
    is a plain concatenation. The model is stateless: it remembers the
    conversation only because we re-send it here, every turn.

    The clock line goes at the END of the system prompt, so the persona text
    before it is the same on every turn; only that line changes. A forced
    reply language's line comes after it, last of all, on its own line.
    """
    system = f"{system_prompt}\n\n{clock_line(now)}"
    if reply_language in REPLY_LANGUAGE_LINES:  # "any" adds nothing
        system += f"\n{REPLY_LANGUAGE_LINES[reply_language]}"
    return [
        Message(role="system", content=system),
        *history,
        Message(role="user", content=transcript),
    ]
