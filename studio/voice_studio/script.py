"""Turning a typed script into sentences, and sentences' audio into one file.

The model is given one sentence at a time, for two reasons. Chatterbox
generates at most 1,000 speech tokens (40 s) per call and its output drifts
on long inputs, so short inputs are both safer and better. And each sentence
can get its own language: one with any Devanagari is "hi", one without is
"en", the same rule the voice agent uses to pick a Piper voice
(vaani/language.py, reused here so the two can never disagree).
"""

import re

import numpy as np
from vaani.language import reply_language

# A sentence ends at ., !, ? or the Devanagari danda (U+0964) or double
# danda (U+0965), followed by white space; a line break always ends one.
# Built with chr() so this file stays ASCII, as in vaani/language.py.
_DANDAS = chr(0x0964) + chr(0x0965)
_SENTENCE_END = re.compile(rf"(?<=[.!?{_DANDAS}])\s+|\s*\n\s*")


class ScriptError(Exception):
    """The script cannot be generated as typed. `code` names why."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def plan(script: str, max_chars: int, max_sentence_chars: int) -> list[tuple[str, str]]:
    """(sentence, language) pairs, in order. Raises ScriptError."""
    text = script.strip()
    if not text:
        raise ScriptError("STUDIO_SCRIPT_EMPTY", "Type a script first.")
    if len(text) > max_chars:
        raise ScriptError(
            "STUDIO_SCRIPT_TOO_LONG",
            f"The script is {len(text)} characters; the limit is {max_chars}. "
            "Shorten it or generate it in parts.",
        )
    sentences = [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]
    for sentence in sentences:
        if len(sentence) > max_sentence_chars:
            raise ScriptError(
                "STUDIO_SENTENCE_TOO_LONG",
                f"One sentence is {len(sentence)} characters; the limit is "
                f"{max_sentence_chars}. Split it with a full stop.",
            )
    return [(s, reply_language(s)) for s in sentences]


def join(waves: list[np.ndarray], rate: int, gap_ms: int) -> np.ndarray:
    """The sentences end to end, with `gap_ms` of silence between them."""
    gap = np.zeros(rate * gap_ms // 1000, dtype=np.float32)
    parts: list[np.ndarray] = []
    for index, wave in enumerate(waves):
        if index:
            parts.append(gap)
        parts.append(wave.astype(np.float32))
    return np.concatenate(parts)
