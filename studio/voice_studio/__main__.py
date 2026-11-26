"""`uv run python -m voice_studio`: start the studio on host:port from config.toml."""

import os

# Chatterbox draws a tqdm progress bar and redraws it for EVERY speech token,
# into the server's log. A server log has no use for it, and it cost time:
# one warm sentence took 2.73 s with the bar and 2.19 s without (one run each,
# docs/findings/voice-studio/notes_20261126.txt). tqdm reads TQDM_DISABLE once,
# when it is first imported, so this must run before any import below.
os.environ.setdefault("TQDM_DISABLE", "1")

import uvicorn  # noqa: E402 (after the environment line above, on purpose)

from voice_studio.config import get_studio_settings  # noqa: E402

if __name__ == "__main__":
    cfg = get_studio_settings()
    # factory=True: uvicorn calls create_app() itself, after it has started.
    uvicorn.run(
        "voice_studio.app:create_app", factory=True, host=cfg.host, port=cfg.port
    )
