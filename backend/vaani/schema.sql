-- The session and turn database: one row per session, one row per turn.
-- Text and numbers only, never audio. Nothing reads it back into a
-- conversation; scripts/turn_stats.py reads it for latency statistics.
--
-- Applied by vaani/db.py on every open. CREATE ... IF NOT EXISTS makes a
-- second run a no-op. The schema's version is PRAGMA user_version, a number
-- SQLite keeps in the file's header: 0 on a new file, 1 after this script.
-- A change to a table bumps it, here and in db.py's SCHEMA_VERSION together.
--
-- STRICT: SQLite then refuses a value of the wrong type (text in a REAL
-- column), instead of storing it anyway as a plain table would.

CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,   -- session_id, as sent in session.started
    started_at  TEXT NOT NULL,      -- UTC wall clock, 'YYYY-MM-DD HH:MM:SS.SSS'
    ended_at    TEXT,               -- same format; NULL while live, or if the server died
    persona     TEXT NOT NULL,      -- a key of [personas]
    mode        TEXT NOT NULL CHECK (mode IN ('vad', 'ptt')),
    -- client_end: session.end; disconnect: socket closed without it;
    -- error: the server's session loop raised. NULL while live.
    end_reason  TEXT CHECK (end_reason IN ('client_end', 'disconnect', 'error'))
) STRICT;

CREATE TABLE IF NOT EXISTS turns (
    id                     TEXT PRIMARY KEY,  -- turn_id
    session_id             TEXT NOT NULL REFERENCES sessions(id),
    turn_index             INTEGER NOT NULL,  -- 1, 2, 3 ... within the session
    -- replied: the reply played to the end (or was sent, if text only).
    -- cut: a barge-in stopped it (by speech or by a ptt press).
    -- empty: nothing to answer (too short, an empty press, no words heard).
    -- failed: error_code says why. closed: the socket closed mid-turn.
    outcome                TEXT NOT NULL
                           CHECK (outcome IN ('replied', 'cut', 'empty', 'failed', 'closed')),
    -- What the model was asked to answer: this turn's transcript, after any
    -- words carried from a cut turn. NULL: no reply started.
    user_text              TEXT,
    -- Script of user_text and of the reply's first chunk, by vaani/language.py:
    -- 'hi' = has Devanagari, 'en' = none. A script, not a language: romanized
    -- Hinglish is 'en'. NULL when there is no text (or no speech, for replies).
    user_script            TEXT CHECK (user_script IN ('hi', 'en')),
    reply_script           TEXT CHECK (reply_script IN ('hi', 'en')),
    reply_generated        TEXT,  -- every delta the model sent, up to a cut
    reply_heard            TEXT,  -- what went into history; NULL if nothing did
    llm_provider           TEXT,  -- [llm].provider_order name that answered
    llm_model              TEXT,  -- the model the provider reported
    error_code             TEXT,  -- ASR_FAILED, LLM_FAILED, TTS_FAILED, INPUT_REJECTED
    -- Milliseconds between two perf_counter spans (vaani/telemetry.py).
    -- NULL: one of the two never happened (not measured).
    end_to_asr_ms          REAL,  -- speech_end -> asr_final
    asr_ms                 REAL,  -- asr_start -> asr_final
    llm_first_token_ms     REAL,  -- llm_request -> llm_first_token
    tts_first_chunk_ms     REAL,  -- tts_start -> tts_first_audio
    end_to_first_audio_ms  REAL,  -- speech_end -> tts_first_audio
    UNIQUE (session_id, turn_index)
) STRICT;

CREATE INDEX IF NOT EXISTS turns_by_session ON turns(session_id);

PRAGMA user_version = 1;
