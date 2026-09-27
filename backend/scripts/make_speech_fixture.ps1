# make_speech_fixture.ps1 — regenerate tests/fixtures/speech_16k_mono.wav.
#
# Silero VAD rejects pure tones and synthetic vowels (they read as "not
# speech"), so tests and fake_client need a real speech clip. This renders one
# with the Windows built-in speech synthesiser (System.Speech / SAPI), directly
# in our wire format: 16 kHz, 16-bit, mono PCM. Windows only; the committed
# WAV itself works everywhere, including Linux CI.
#
# Run from backend/:
#     powershell -File scripts/make_speech_fixture.ps1

$out = Join-Path $PSScriptRoot "..\tests\fixtures\speech_16k_mono.wav"
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
    16000,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono
)
$synth.SetOutputToWaveFile($out, $format)
$synth.Speak("Hello, this is a short test of voice activity detection for the Vaani project.")
$synth.Dispose()
Write-Output "wrote $out"
