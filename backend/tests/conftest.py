"""Shared pytest setup.

Speech recognition is switched OFF for the test process by default, before
any test module imports vaani.app (which builds an app at import time). With
it on, every test would load a Whisper model: hundreds of MB to download in
CI and seconds of startup. Tests that need the real model pass an explicit
`asr=` setting (constructor arguments beat environment variables) and are
marked @pytest.mark.slow; gateway tests inject a fake recogniser instead.
"""

import os

os.environ["VAANI_ASR__ENABLED"] = "false"
