"""Protocol v0.10: session.start's reply_language, through the gateway.

Fakes as in test_voice_route.py: the real VAD and endpointer on the speech
fixture, the fake recogniser, a scripted model that records every request,
and two fake voices at DIFFERENT rates, so audio.start's sample_rate proves
which voice spoke. The persona prompt text is config.toml's real one.
"""

import logging

import pytest

import vaani.turns as turns_mod
from tests.fake_tts import FakeSynthesizer
from tests.test_asr_gateway import START
from tests.test_barge_in import say
from tests.test_ptt import CountingVad
from tests.test_turn_llm import ScriptedLLM, speak
from tests.test_turn_log import connect, rows
from tests.test_turn_tts import is_, make_client, until
from tests.test_voice_route import ENGLISH_RATE, HINDI_RATE, spoken_rate
from vaani.persona import REPLY_LANGUAGE_LINES


def one_turn(starts: list[dict], chunks=("Theek hai.",)):
    """Send each session.start in `starts` (each answered), then one turn.

    Returns the session.started replies, the system prompt the model got,
    the two fake voices and every message from the turn up to idle.
    """
    voices = {
        "hi": FakeSynthesizer(sample_rate=HINDI_RATE, audio_ms_per_char=10),
        "en": FakeSynthesizer(sample_rate=ENGLISH_RATE, audio_ms_per_char=10),
    }
    llm = ScriptedLLM(chunks)
    client = make_client(llm, voices["hi"])
    client.app.state.synthesizers = {"default": voices}
    with client.websocket_connect("/ws/session") as ws:
        started = []
        for fields in starts:
            ws.send_json({**START, **fields})
            started.append(ws.receive_json())
        speak(ws)
        msgs = until(ws, is_("idle"))
    [system, *_] = llm.calls[0]  # the turn's one request; system comes first
    return started, system.content, voices, msgs


# --- The field ------------------------------------------------------------------


@pytest.mark.parametrize(
    "fields, echoed",
    [({}, "any"), ({"reply_language": "en"}, "en"), ({"reply_language": "hi"}, "hi")],
)
def test_session_started_echoes_the_reply_language(fields, echoed) -> None:
    with make_client(ScriptedLLM(), FakeSynthesizer()).websocket_connect(
        "/ws/session"
    ) as ws:
        ws.send_json({**START, **fields})
        started = ws.receive_json()
    assert started["type"] == "session.started"
    assert started["reply_language"] == echoed


@pytest.mark.parametrize("value", ["fr", "EN", "english", 1])
def test_an_unknown_reply_language_is_a_bad_message(value) -> None:
    with make_client(ScriptedLLM(), FakeSynthesizer()).websocket_connect(
        "/ws/session"
    ) as ws:
        ws.send_json({**START, "reply_language": value})
        reply = ws.receive_json()
        ws.send_bytes(b"\x00" * 640)  # no session was made
        after = ws.receive_json()
    assert reply["type"] == "error" and reply["code"] == "BAD_MESSAGE"
    assert after["code"] == "SESSION_NOT_STARTED"


def test_a_second_session_start_keeps_the_first_reply_language() -> None:
    started, system, _, _ = one_turn(
        [{"reply_language": "hi"}, {"reply_language": "en"}]
    )
    assert started[1] == started[0]  # same session_id, still "hi"
    assert started[0]["reply_language"] == "hi"
    assert system.endswith("\n" + REPLY_LANGUAGE_LINES["hi"])


# --- The prompt -----------------------------------------------------------------


@pytest.mark.parametrize("language", ["en", "hi"])
def test_a_forced_language_line_lands_last_after_the_clock(language) -> None:
    _, system, _, _ = one_turn([{"reply_language": language}])
    *_, clock, last = system.split("\n")
    assert clock.startswith("Current date and time (")
    assert last == REPLY_LANGUAGE_LINES[language]


def test_any_adds_no_reply_language_line() -> None:
    _, system, _, _ = one_turn([{"reply_language": "any"}])
    assert system.split("\n")[-1].startswith("Current date and time (")
    assert "Reply language:" not in system


# --- The voice ------------------------------------------------------------------


def test_forced_hindi_says_a_reply_starting_ok_with_the_hindi_voice(caplog) -> None:
    # Under "any" the first chunk "OK," would pick the English voice for the
    # whole reply (test_voice_route.py). Forced Hindi keeps the Hindi voice.
    with caplog.at_level(logging.WARNING, logger="vaani.speaker"):
        _, _, voices, msgs = one_turn(
            [{"reply_language": "hi"}], chunks=("OK, ", "ठीक है।")
        )
    assert voices["hi"].texts == ["OK,", "ठीक है।"]
    assert voices["en"].texts == []
    assert spoken_rate(msgs) == HINDI_RATE
    assert "forced hi reply began in en script" in caplog.text
    assert "script drift" not in caplog.text  # the second chunk IS Hindi


def test_forced_english_says_a_devanagari_reply_with_the_english_voice(
    caplog,
) -> None:
    with caplog.at_level(logging.WARNING, logger="vaani.speaker"):
        _, _, voices, msgs = one_turn([{"reply_language": "en"}], chunks=("ठीक है।",))
    assert voices["en"].texts == ["ठीक है।"]
    assert voices["hi"].texts == []
    assert spoken_rate(msgs) == ENGLISH_RATE
    assert "forced en reply began in hi script" in caplog.text


def test_a_forced_reply_in_its_own_script_logs_nothing(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="vaani.speaker"):
        _, _, voices, _ = one_turn([{"reply_language": "en"}], chunks=("Sure.",))
    assert voices["en"].texts == ["Sure."]
    assert "forced" not in caplog.text


def test_the_row_keeps_the_first_chunks_script_not_the_forced_voice(
    tmp_path, monkeypatch
) -> None:
    # schema.sql: reply_script is the SCRIPT of the reply's first chunk.
    # test_turn_log.py's helpers drive the scripted VAD, so install it here.
    monkeypatch.setattr(turns_mod, "VadStream", CountingVad)
    with connect(tmp_path, reply_language="hi", chunks=("OK, ", "ठीक है।")) as ws:
        say(ws)
        until(ws, is_("idle"))
    [turn] = rows(tmp_path, "turns")
    assert turn["reply_script"] == "en"
