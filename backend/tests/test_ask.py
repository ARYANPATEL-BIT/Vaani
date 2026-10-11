"""scripts/ask.py's self-name check: a persona may name its role, never a name.

ask.py is a script, not a package module, so it is loaded from its file the
way test_fake_client.py loads fake_client.py.
"""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ask.py"


def load_ask():
    spec = importlib.util.spec_from_file_location("ask", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_asked_my_name_is_not_a_self_name():
    # qwen's reply, verbatim, that the old pattern flagged with "पूछा"
    # (docs/findings/groq-primary/ask_after_groq_tutor_20261008-103752.txt).
    reply = (
        "मुझे प्रसन्न हो रहा है कि आपसे मिलकर। आपने मेरा नाम पूछा है इसलिए "
        "मैं आपको बताता हूँ। मैं आपका ट्यूटर हूँ।"
    )
    said, not_roles = load_ask().self_names(reply)
    assert (said, not_roles) == (1, [])  # only "मैं आपका ट्यूटर हूँ"


def test_you_asked_my_name_alone_passes():
    # The bare sentence: no self-description at all, so nothing to flag.
    assert load_ask().self_names("आपने मेरा नाम पूछा है।") == (0, [])


def test_a_real_name_still_fails():
    assert load_ask().self_names("मैं राहुल हूँ।") == (1, ["राहुल"])


def test_my_name_is_still_caught():
    # The pattern the fix narrowed must still catch a plain statement.
    assert load_ask().self_names("मेरा नाम राहुल है।") == (1, ["राहुल"])
