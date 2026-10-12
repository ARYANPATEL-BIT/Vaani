"""Shared pytest setup.

Speech recognition is switched OFF for the test process by default, before
any test module imports vaani.app (which builds an app at import time). With
it on, every test would load a Whisper model: hundreds of MB to download in
CI and seconds of startup. Tests that need the real model pass an explicit
`asr=` setting (constructor arguments beat environment variables) and are
marked @pytest.mark.slow; gateway tests inject a fake recogniser instead.

The language model is off for the same reason, and because CI has no API
keys: build_chain refuses to start without them. Tests that need a model
inject a scripted one (tests/test_turn_llm.py).

Speech synthesis is off too: gateway tests inject a fake synthesiser
(tests/fake_tts.py). tests/test_tts_piper.py builds the real voice directly.

The database is off too, so no test writes to backend/data/vaani.db; the
database tests pass a temporary file (tests/test_db.py).
"""

import os

os.environ["VAANI_ASR__ENABLED"] = "false"
os.environ["VAANI_LLM__ENABLED"] = "false"
os.environ["VAANI_TTS__ENABLED"] = "false"
os.environ["VAANI_DB__ENABLED"] = "false"
