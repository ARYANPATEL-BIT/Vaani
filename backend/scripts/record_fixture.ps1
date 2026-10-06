# Record the real Hinglish test clip: backend/tests/fixtures/hinglish_real_16k.wav
# 16000 Hz, mono, 16-bit PCM WAV, the format the server expects from the mic.
#
# Uses MCI (Media Control Interface), a recorder built into Windows (winmm.dll),
# so nothing has to be installed. MCI is driven by text commands
# ("open", "set", "record", "save") sent through one function, mciSendString.
# Each call returns 0 on success, or an MCI error number.
#
# Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File backend\scripts\record_fixture.ps1
# Optional: -Seconds 6 (default 8).

param([int]$Seconds = 8)

$ErrorActionPreference = 'Stop'

# Make mciSendString callable from PowerShell.
$mci = Add-Type -Name Mci -Namespace VaaniRecord -PassThru -MemberDefinition @'
[DllImport("winmm.dll", CharSet = CharSet.Unicode)]
public static extern int mciSendString(string command, System.Text.StringBuilder result, int length, System.IntPtr callback);
'@

function Send-Mci([string]$command) {
    $code = $mci::mciSendString($command, $null, 0, [System.IntPtr]::Zero)
    if ($code -ne 0) {
        # Close the device so a failed run does not leave it open.
        $null = $mci::mciSendString('close rec', $null, 0, [System.IntPtr]::Zero)
        throw "MCI command failed (error $code): $command"
    }
}

# backend/scripts -> backend/tests/fixtures
$out = Join-Path $PSScriptRoot '..\tests\fixtures\hinglish_real_16k.wav'
$out = [System.IO.Path]::GetFullPath($out)

Send-Mci 'open new type waveaudio alias rec'
# The format must be set before recording starts. bytespersec and alignment
# follow from the other three: 16000 samples x 2 bytes x 1 channel.
Send-Mci 'set rec bitspersample 16 channels 1 samplespersec 16000 bytespersec 32000 alignment 2'

Write-Host "Recording $Seconds s from the default microphone. Speak now."
Send-Mci 'record rec'
Start-Sleep -Seconds $Seconds
Send-Mci 'stop rec'

# The path is quoted because it contains a space ("Aryan Patel").
Send-Mci "save rec `"$out`""
Send-Mci 'close rec'
Write-Host "Saved $out"
