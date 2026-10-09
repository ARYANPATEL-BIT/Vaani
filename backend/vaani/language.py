"""Which language a piece of reply text is in, judged by its SCRIPT.

The persona prompt tells the model to write an all-English reply in Latin
script and a Hindi or mixed reply in Devanagari. So the script the model
actually wrote is what picks the voice, whatever language it meant to use.
A voice given the other script is not silent: espeak-ng switches its
phoneme rules by script, so the English voice gets Hindi phonemes for
Devanagari and the Hindi voice English ones for Latin. But each voice was
trained on one language's speech only, and says the other's sounds badly:
Latin Hinglish through the Hindi voice was rated unintelligible on day 12
(docs/learning/backend-learning/12-chunking-tts.md).

One Devanagari character is enough for "hi": a mixed reply stays on the
Hindi voice. Text with no Devanagari at all is "en".
"""

import re

# The language keys of [tts.piper.voices.<persona>]: every persona has a
# voice for each. reply_language only ever returns one of these.
LANGUAGES = ("hi", "en")

# The Devanagari Unicode block, U+0900 to U+097F. Built with chr() so the
# source shows the code points, as in chunker.py.
_DEVANAGARI = re.compile(f"[{chr(0x0900)}-{chr(0x097F)}]")


def reply_language(text: str) -> str:
    """The language key for `text`: "hi" if it has any Devanagari, else "en"."""
    return "hi" if _DEVANAGARI.search(text) else "en"
