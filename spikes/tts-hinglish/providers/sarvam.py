"""Future Sarvam Bulbul TTS provider adapter boundary.

This adapter represents the planned cloud-based TTS provider boundary.
It defines the required configuration schema and integration points for
Sarvam Bulbul (v2), but is intentionally NOT implemented in Week 1 Day 5.

No network requests are made, and no API keys are required for the current project.
Credentials and implementation will be added in a future phase.
"""

from .base import (
    AuthenticationError,
    TTSProvider,
    TTSResult,
)


class SarvamTTSProvider(TTSProvider):
    """Adapter boundary for Sarvam Bulbul TTS API (planned for future phase).

    Configuration contract:
      - api_key: Sarvam subscription API key (from environment, never hardcoded)
      - speaker: Target voice speaker (e.g. 'anushka')
      - model: Target model version (e.g. 'bulbul:v2')
      - sample_rate: Output sample rate (e.g. 16000)
    """

    def __init__(
        self,
        api_key: str | None = None,
        speaker: str = "anushka",
        model: str = "bulbul:v2",
        sample_rate: int = 16000,
        endpoint_url: str = "https://api.sarvam.ai/text-to-speech",
    ) -> None:
        self.api_key = api_key
        self.speaker = speaker
        self.model = model
        self.sample_rate = sample_rate
        self.endpoint_url = endpoint_url

    @property
    def name(self) -> str:
        return "sarvam"

    def is_available(self) -> bool:
        # Intentionally returns False in current state since not integrated.
        return bool(self.api_key)

    def synthesize(self, text: str) -> TTSResult:
        """Adapter boundary stub.

        Raises NotImplementedError to ensure zero network requests are made
        during Day 5 local execution.
        """
        if not self.api_key:
            raise AuthenticationError(
                "Sarvam API key is not configured. Sarvam integration is deferred "
                "to a future phase; use the 'piper' provider for live speech."
            )
        raise NotImplementedError(
            "Sarvam TTS provider adapter is not implemented for Week 1 Day 5. "
            "Piper is the active, verified local engine."
        )
