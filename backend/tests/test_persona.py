"""The date and time line persona.assemble adds to every system prompt.

The model has no clock, so the server tells it the date and time on every
turn ([llm].timezone). The line goes after the persona text, so that text is
the same on every turn.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from vaani.config import Settings
from vaani.persona import assemble
from vaani.providers.base import Message


def test_the_clock_line_ends_the_system_prompt() -> None:
    now = datetime(2026, 10, 14, 14, 5, tzinfo=ZoneInfo("Asia/Kolkata"))
    history = [Message("user", "hi"), Message("assistant", "Hello!")]

    messages = assemble("You are a tutor.", history, "what's the date?", now)

    assert messages[0] == Message(
        "system",
        "You are a tutor.\n\n"
        "Current date and time (Asia/Kolkata): Wednesday, 14 October 2026, 14:05.",
    )
    # Only the system prompt changes: history and the turn are as before.
    assert messages[1:] == [*history, Message("user", "what's the date?")]


def test_an_unknown_time_zone_stops_startup(monkeypatch) -> None:
    monkeypatch.setenv("VAANI_LLM__TIMEZONE", "Asia/Nowhere")
    with pytest.raises(ValidationError, match="unknown time zone"):
        Settings()
