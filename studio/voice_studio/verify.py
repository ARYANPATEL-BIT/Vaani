"""ETH-2: the live challenge phrase, and the two checks run on it.

Why a challenge at all: a voice sample alone proves nothing about who
uploaded it, since anyone can download a clip of someone else. So the
studio shows a phrase that did not exist a moment ago (random words) and the
user reads it aloud, live. Two checks then have to pass:

1. WHAT was said: Whisper transcribes the recording and enough of the
   phrase's words must be in it. A pre-recorded clip cannot contain words
   that were drawn after it was made.
2. WHO said it: the challenge recording and the voice sample must come from
   the same speaker (cosine similarity of their speaker embeddings). Reading
   the phrase yourself while uploading someone else's sample fails here.

The phrases live in memory only, one per user, and are forgotten on success,
on expiry, on delete and on restart. Nothing about them needs to persist.
"""

import re
import secrets
import time
from dataclasses import dataclass

import numpy as np

_WORD = re.compile(r"[a-z]+")
# secrets, not random: the phrase must not be predictable from earlier ones.
_RNG = secrets.SystemRandom()


@dataclass(frozen=True)
class Challenge:
    phrase: str
    issued_at: float  # time.monotonic(), immune to the wall clock changing


def new_challenge(words: list[str], count: int) -> Challenge:
    """`count` distinct words from `words`, in a random order."""
    return Challenge(" ".join(_RNG.sample(words, count)), time.monotonic())


def is_live(challenge: Challenge | None, ttl_s: float) -> bool:
    return challenge is not None and time.monotonic() - challenge.issued_at < ttl_s


def words_of(text: str) -> list[str]:
    """Lowercase ASCII words; Whisper's punctuation and capitals are dropped."""
    return _WORD.findall(text.lower())


def phrase_match(phrase: str, transcript: str) -> float:
    """Share of the phrase's words that appear in the transcript (0 to 1).

    Order is not checked: Whisper sometimes drops or merges a word, and a
    replayed recording cannot have the right words in ANY order anyway.
    """
    expected = words_of(phrase)
    heard = set(words_of(transcript))
    return sum(word in heard for word in expected) / len(expected)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two embeddings: 1.0 means the same direction."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
