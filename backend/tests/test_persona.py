"""The lines persona.assemble adds to every system prompt.

The model has no clock, so the server tells it the date and time on every
turn ([llm].timezone). The line goes after the persona text, so that text is
the same on every turn. A session that forces a reply language (protocol
v0.10) gets one more line after it; "any" gets none.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from vaani.config import Settings
from vaani.persona import assemble
from vaani.providers.base import Message

NOW = datetime(2026, 10, 14, 14, 5, tzinfo=ZoneInfo("Asia/Kolkata"))
CLOCK = "Current date and time (Asia/Kolkata): Wednesday, 14 October 2026, 14:05."


def test_the_clock_line_ends_the_system_prompt() -> None:
    history = [Message("user", "hi"), Message("assistant", "Hello!")]

    messages = assemble("You are a tutor.", history, "what's the date?", NOW, "any")

    # "any": nothing after the clock line, exactly as before v0.10.
    assert messages[0] == Message("system", f"You are a tutor.\n\n{CLOCK}")
    # Only the system prompt changes: history and the turn are as before.
    assert messages[1:] == [*history, Message("user", "what's the date?")]


@pytest.mark.parametrize(
    "reply_language, line",
    [
        ("en", "Reply language: English (Latin script)."),
        ("hi", "Reply language: Hindi (Devanagari script)."),
    ],
)
def test_a_forced_reply_language_is_the_last_line(reply_language, line) -> None:
    messages = assemble("You are a tutor.", [], "hello", NOW, reply_language)

    assert messages[0] == Message("system", f"You are a tutor.\n\n{CLOCK}\n{line}")


def test_every_persona_prompt_obeys_the_line_and_finds_the_clock_by_name() -> None:
    # The rule must quote the line's own opening words, or the model is told
    # to obey a line it cannot recognise. And "the last line" is no longer
    # the clock once a reply-language line follows it.
    for persona, prompt in Settings().personas.items():
        assert '"Reply language" line ends this prompt' in prompt, persona
        assert '"Current date and time" line' in prompt, persona
        assert "last line of this prompt" not in prompt, persona


def test_an_unknown_time_zone_stops_startup(monkeypatch) -> None:
    monkeypatch.setenv("VAANI_LLM__TIMEZONE", "Asia/Nowhere")
    with pytest.raises(ValidationError, match="unknown time zone"):
        Settings()
