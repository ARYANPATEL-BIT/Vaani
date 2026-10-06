"""Clause chunking: cut the streamed reply into pieces worth synthesising.

Text only, no clock: a pause in the token stream never cuts a chunk, only
the text does. Boundaries, best first: sentence end, clause break,
conjunction, then any space once a chunk is too long.

THE FIRST CHUNK PLAYS BY DIFFERENT RULES. It is the only chunk the user waits
for, so it is cut at the EARLIEST boundary of any kind once it is long enough.
Every later chunk is synthesised while earlier audio plays, so it waits for a
sentence end, which keeps each sentence's intonation whole.
"""

import re

from vaani.config import ChunkerSettings

# . ? ! or the Devanagari danda, FOLLOWED BY WHITESPACE. The whitespace keeps
# "3.5" whole, and means an end is only seen once the next token arrives.
_SENTENCE = re.compile(r"[.?!।]+(?=\s)")
_CLAUSE = re.compile(r"(?:[,;:]|--)(?=\s)")


class ClauseChunker:
    """One reply's chunker: push() each text delta, flush() at the end."""

    def __init__(self, cfg: ChunkerSettings) -> None:
        self._cfg = cfg
        self._abbreviations = {a.lower() for a in cfg.abbreviations}
        words = "|".join(re.escape(w) for w in cfg.conjunctions)
        # Matches the space in FRONT of a conjunction: the cut goes there, so
        # "but ..." starts the next chunk, as it would in speech.
        self._conjunction = re.compile(rf"\s(?=(?:{words})\b)", re.IGNORECASE)
        self._buf = ""
        self._first = True

    def push(self, delta: str) -> list[str]:
        """Add a delta; return the chunks it completed (often none)."""
        self._buf += delta
        chunks = []
        while (cut := self._find_cut()) is not None:
            chunk = self._buf[:cut].strip()
            # lstrip: the rest never starts with the space a cut was made at.
            self._buf = self._buf[cut:].lstrip()
            if chunk:
                chunks.append(chunk)
                self._first = False
        return chunks

    def flush(self) -> str | None:
        """The reply is complete: whatever is left is the last chunk."""
        chunk, self._buf = self._buf.strip(), ""
        return chunk or None

    def _find_cut(self) -> int | None:
        """Where to cut the buffer now, or None to keep waiting."""
        buf, cfg = self._buf, self._cfg
        if self._first:
            ends = [e for kind in self._boundaries(buf) for e in kind]
            early_enough = [e for e in ends if e >= cfg.first_min_chars]
            if early_enough:
                return min(early_enough)
            return self._last_space(cfg.first_max_chars)
        sentences, _, _ = self._boundaries(buf)
        if sentences:
            return sentences[0]
        if len(buf) <= cfg.max_chars:
            return None
        _, clauses, conjunctions = self._boundaries(buf[: cfg.max_chars])
        for ends in (clauses, conjunctions):
            if ends:
                return ends[-1]
        return self._last_space(cfg.max_chars)

    def _boundaries(self, text: str) -> tuple[list[int], list[int], list[int]]:
        """Cut positions in `text`: sentence ends, clause breaks, conjunctions."""
        sentences = []
        for m in _SENTENCE.finditer(text):
            before = text[: m.start()].split()
            word = before[-1].lower() if before else ""
            if m.group() == "." and word in self._abbreviations:
                continue  # "Dr." is not a sentence end
            sentences.append(m.end())
        clauses = [m.end() for m in _CLAUSE.finditer(text)]
        conjunctions = [m.start() for m in self._conjunction.finditer(text)]
        return sentences, clauses, conjunctions

    def _last_space(self, limit: int) -> int | None:
        """The last space before `limit`, once the buffer has passed it."""
        if len(self._buf) <= limit:
            return None
        cut = self._buf.rfind(" ", 0, limit)
        return cut if cut > 0 else None
