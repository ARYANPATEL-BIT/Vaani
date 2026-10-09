"""Day 12: clause chunking of the streamed reply.

Replies are fed the way the model streams them: a few characters at a time,
split at arbitrary points, so a boundary often arrives across two pushes.
"""

import re

from vaani.chunker import ClauseChunker
from vaani.config import Settings

CFG = Settings().chunker


def chunk(deltas: list[str], **cfg) -> list[str]:
    """Feed `deltas` one by one, then flush; return every chunk cut."""
    chunker = ClauseChunker(CFG.model_copy(update=cfg))
    out = []
    for delta in deltas:
        out += chunker.push(delta)
    if (last := chunker.flush()) is not None:
        out.append(last)
    return out


def tokens(text: str) -> list[str]:
    """Split like a model's stream: words with their trailing space."""
    return re.findall(r"\S+\s*", text)


def test_a_pause_inside_a_sentence_does_not_split_it() -> None:
    # The model stalls after "Main aapko" (a pause in time). The chunker has
    # no clock, so only text can cut: nothing is emitted during the stall.
    chunker = ClauseChunker(CFG)
    assert chunker.push("Main aapko") == []
    assert chunker.push(" kal subah") == []  # still no boundary: still waiting
    assert chunker.push(" yaad dila doongi.") == []  # end not confirmed yet
    assert chunker.flush() == "Main aapko kal subah yaad dila doongi."


def test_decimal_point_is_not_a_sentence_end() -> None:
    text = "Aapka bill 3.5 hazaar ka hai. Kal tak bhar dijiye."
    # Split so that "3." and "5" arrive in different pushes.
    deltas = ["Aapka bill 3.", "5 hazaar ka hai. ", "Kal tak bhar dijiye."]
    assert chunk(deltas) == ["Aapka bill 3.5 hazaar ka hai.", "Kal tak bhar dijiye."]
    assert chunk(tokens(text)) == chunk(deltas)


def test_abbreviation_is_not_a_sentence_end() -> None:
    text = "Theek hai, aapka appointment Dr. Sharma ke saath hai. Woh 5 baje aayenge."
    assert chunk(tokens(text)) == [
        "Theek hai,",
        "aapka appointment Dr. Sharma ke saath hai.",
        "Woh 5 baje aayenge.",
    ]


def test_an_english_time_is_not_a_sentence_end() -> None:
    # English replies (feat/english-voice): "a.m." must not cut the sentence.
    text = "Sure. I'll remind you at 8 a.m. tomorrow. Anything else?"
    assert chunk(tokens(text)) == [
        "Sure.",
        "I'll remind you at 8 a.m. tomorrow.",
        "Anything else?",
    ]


def test_first_chunk_is_shorter_than_later_chunks() -> None:
    text = (
        "Theek hai, main kal subah aath baje aapko yaad dila doongi. "
        "Aur agar aap chahein toh main ek message bhi bhej sakti hoon."
    )
    chunks = chunk(tokens(text))
    assert chunks[0] == "Theek hai,"  # the earliest boundary, a comma
    assert all(len(chunks[0]) < len(later) for later in chunks[1:])
    # Later chunks are whole sentences, even with commas inside them.
    assert chunks[1:] == [
        "main kal subah aath baje aapko yaad dila doongi.",
        "Aur agar aap chahein toh main ek message bhi bhej sakti hoon.",
    ]


def test_a_clause_break_cuts_the_first_chunk_at_any_length() -> None:
    # "जी," is 3 characters, under first_min_chars (8), but a comma is a pause.
    assert chunk(tokens("जी, मैं आ रही हूँ।")) == ["जी,", "मैं आ रही हूँ।"]
    assert chunk(tokens("Haan, main aa rahi hoon.")) == ["Haan,", "main aa rahi hoon."]


def test_a_conjunction_waits_until_the_first_chunk_has_first_min_chars() -> None:
    # "हाँ" is 3 characters: a cut before "तो" would leave a fragment with no
    # pause after it, so the first chunk waits.
    text = "हाँ तो मैं कल आ जाऊँगी।"
    assert chunk(tokens(text)) == [text]


def test_a_sentence_end_cuts_the_first_chunk_below_first_min_chars() -> None:
    # "Hello!" is 6 characters, under first_min_chars (8), but a whole sentence.
    chunker = ClauseChunker(CFG)
    out = []
    for delta in tokens("Hello! Ye test bhi badhiya se kaam kar gaya hai."):
        out += chunker.push(delta)
    assert out == ["Hello!"]
    assert chunker.first_rule == "sentence end"


def test_first_rule_names_the_boundary_that_cut() -> None:
    chunker = ClauseChunker(CFG)
    for delta in tokens("Theek hai, main kal yaad dila doongi."):
        chunker.push(delta)
    assert chunker.first_rule == "clause break"


def test_punctuation_alone_is_never_a_chunk() -> None:
    # "..." would be a sentence end, but has no letter: it joins the next chunk.
    assert chunk(tokens("... Haan, main aa rahi hoon."))[0] == "... Haan,"
    # Left over at the end, it is dropped: there is nothing to say.
    assert chunk(tokens("Theek hai. ...")) == ["Theek hai."]


def test_devanagari_conjunctions_cut_the_first_chunk() -> None:
    for word in ["लेकिन", "क्योंकि", "तो"]:
        text = f"मुझे नहीं पता {word} मैं पता कर सकती हूँ।"
        assert chunk(tokens(text)) == ["मुझे नहीं पता", f"{word} मैं पता कर सकती हूँ।"]


def test_a_conjunction_inside_a_devanagari_word_is_not_a_cut() -> None:
    # "तोड़" (break) starts with "तो". A \b regex cut there, because Python
    # counts the vowel sign ो as a non-word character.
    text = "उसने गलती से खिलौना तोड़ दिया।"
    assert chunk(tokens(text)) == [text]


def test_first_chunk_can_be_cut_before_a_conjunction() -> None:
    text = "Mujhe nahi pata lekin main pata kar sakti hoon."
    assert chunk(tokens(text)) == ["Mujhe nahi pata", "lekin main pata kar sakti hoon."]


def test_ki_is_not_a_conjunction() -> None:
    # Mostly possessive in Hinglish; cutting there splits a noun phrase.
    text = "Mere dost Ram ki kitaab mez par hai."
    assert chunk(tokens(text)) == [text]
    # Control: with "ki" in the list the same reply WOULD be cut, so the
    # assertion above is testing the list, not an accident of lengths.
    with_ki = chunk(tokens(text), conjunctions=[*CFG.conjunctions, "ki"])
    assert with_ki == ["Mere dost Ram", "ki kitaab mez par hai."]


def test_devanagari_danda_ends_a_sentence() -> None:
    text = "नमस्ते, आज हम real-time voice के बारे में बात करेंगे। यह बहुत interesting है।"
    chunks = chunk(tokens(text))
    assert chunks[0] == "नमस्ते,"  # a clause break cuts the first chunk
    assert chunks[-1] == "यह बहुत interesting है।"
    assert all(c.endswith("।") for c in chunks[1:])


def test_first_chunk_with_no_boundary_is_cut_at_a_space() -> None:
    words = "ek do teen char paanch chhe saat aath nau das " * 3
    first = chunk(tokens(words))[0]
    assert len(first) <= CFG.first_max_chars
    assert not first.endswith(" ") and words.startswith(first + " ")


def test_long_later_chunk_falls_back_to_a_clause_break() -> None:
    long_clause = "yeh ek bahut lamba hissa hai " * 4  # ~116 characters
    text = f"Theek hai, {long_clause}, {long_clause} aur phir khatam."
    chunks = chunk(tokens(text), max_chars=150)
    # No sentence end within 150 characters: cut at the last comma instead.
    assert chunks[1].endswith(",")
    assert all(len(c) <= 150 for c in chunks)


def test_everything_said_exactly_once() -> None:
    text = "Haan ji. Main aapki madad karungi, lekin pehle order number batayiye!"
    chunks = chunk(tokens(text))
    assert " ".join(chunks) == text
