"""Clause chunking: cut the streamed reply into pieces worth synthesising.

Text only, no clock: a pause in the token stream never cuts a chunk, only
the text does. Boundaries, best first: sentence end, clause break,
conjunction, then any space once a chunk is too long.

THE FIRST CHUNK PLAYS BY DIFFERENT RULES. It is the only chunk the user waits
for, so it is cut at the EARLIEST boundary: a sentence end or a clause break
at any length ("Hello!", "जी,"), a conjunction once the chunk is long
enough. Every later chunk is
synthesised while earlier audio plays, so it waits for a sentence end, which
keeps each sentence's intonation whole.

A chunk is never only punctuation ("...", "!"): a cut counts only after the
first letter, so a letterless start stays in the buffer and joins the next
chunk.
"""

import re

from vaani.config import ChunkerSettings

# . ? ! or the Devanagari danda, FOLLOWED BY WHITESPACE. The whitespace keeps
# "3.5" whole, and means an end is only seen once the next token arrives.
_SENTENCE = re.compile(r"[.?!।]+(?=\s)")
_CLAUSE = re.compile(r"(?:[,;:]|--)(?=\s)")
# The Devanagari Unicode block (U+0900 to U+097F), as a regex range. Built
# with chr() so the source shows the code points, not invisible marks.
_DEVANAGARI = f"{chr(0x0900)}-{chr(0x097F)}"


class ClauseChunker:
    """One reply's chunker: push() each text delta, flush() at the end."""

    def __init__(self, cfg: ChunkerSettings) -> None:
        self._cfg = cfg
        self._abbreviations = {a.lower() for a in cfg.abbreviations}
        words = "|".join(re.escape(w) for w in cfg.conjunctions)
        # Matches the space in FRONT of a conjunction: the cut goes there, so
        # "but ..." starts the next chunk, as it would in speech. The word must
        # not run on into more letters ("so" is not "soon", "तो" is not
        # "तोड़"). Not \b: Python counts Devanagari vowel signs (the ो in तो)
        # as non-word characters, so \b would sit INSIDE a Devanagari word.
        self._conjunction = re.compile(
            rf"\s(?=(?:{words})(?![\w{_DEVANAGARI}]))", re.IGNORECASE
        )
        self._buf = ""
        self._first = True
        # Which rule cut the first chunk, for reply.py's debug log.
        self.first_rule: str | None = None

    def push(self, delta: str) -> list[str]:
        """Add a delta; return the chunks it completed (often none)."""
        self._buf += delta
        chunks = []
        while (found := self._find_cut()) is not None:
            cut, rule = found
            chunk = self._buf[:cut].strip()
            # lstrip: the rest never starts with the space a cut was made at.
            self._buf = self._buf[cut:].lstrip()
            if chunk:
                chunks.append(chunk)
                if self._first:
                    self.first_rule = rule
                self._first = False
        return chunks

    def flush(self) -> str | None:
        """The reply is complete: whatever is left is the last chunk."""
        chunk, self._buf = self._buf.strip(), ""
        if not any(c.isalpha() for c in chunk):
            return None  # only punctuation left: nothing to say
        if self._first:
            self.first_rule = "end of reply"
        return chunk

    def _find_cut(self) -> tuple[int, str] | None:
        """Where to cut the buffer now and by which rule, or None to wait."""
        buf, cfg = self._buf, self._cfg
        sentences, clauses, conjunctions = self._boundaries(buf)
        if self._first:
            # A sentence end or a comma cuts at any length: "Hello!" and
            # "जी," are each said with a pause after them (day 14: replies
            # open with "जी," / "ठीक है," and waited for the whole reply).
            # A conjunction only once the chunk has first_min_chars: it has
            # no pause of its own, so a 3-character cut would be a fragment.
            cuts = [(e, "sentence end") for e in sentences]
            cuts += [(e, "clause break") for e in clauses]
            cuts += [
                (e, "conjunction") for e in conjunctions if e >= cfg.first_min_chars
            ]
            if cuts:
                return min(cuts)  # the earliest position
            cut = self._last_space(cfg.first_max_chars)
            return None if cut is None else (cut, "word boundary")
        if sentences:
            return sentences[0], "sentence end"
        if len(buf) <= cfg.max_chars:
            return None
        _, clauses, conjunctions = self._boundaries(buf[: cfg.max_chars])
        for ends in (clauses, conjunctions):
            if ends:
                return ends[-1], "max"
        cut = self._last_space(cfg.max_chars)
        return None if cut is None else (cut, "max")

    def _boundaries(self, text: str) -> tuple[list[int], list[int], list[int]]:
        """Cut positions in `text`: sentence ends, clause breaks, conjunctions.

        Only positions after the first letter count, so "..." on its own is
        never a chunk: it waits in the buffer and joins the next one.
        """
        letter = next((i for i, c in enumerate(text) if c.isalpha()), len(text))
        sentences = []
        for m in _SENTENCE.finditer(text):
            before = text[: m.start()].split()
            word = before[-1].lower() if before else ""
            if m.group() == "." and word in self._abbreviations:
                continue  # "Dr." is not a sentence end
            if m.end() > letter:
                sentences.append(m.end())
        clauses = [m.end() for m in _CLAUSE.finditer(text) if m.end() > letter]
        conjunctions = [
            m.start() for m in self._conjunction.finditer(text) if m.start() > letter
        ]
        return sentences, clauses, conjunctions

    def _last_space(self, limit: int) -> int | None:
        """The last space before `limit`, once the buffer has passed it."""
        if len(self._buf) <= limit:
            return None
        cut = self._buf.rfind(" ", 0, limit)
        return cut if cut > 0 else None
