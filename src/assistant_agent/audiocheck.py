"""Verify mic + speaker before a voice session (the WSL2 audio risk).

Records a few seconds from the default input and plays it back, using the same raw
PCM byte streams (RawInputStream/RawOutputStream) the live voice session uses — so this
exercises the real audio path and needs no NumPy. sounddevice is imported inside the
function so a missing PortAudio yields a friendly message instead of an import crash.
"""

from __future__ import annotations


def run(seconds: int = 3, rate: int = 16000, blocksize: int = 1600) -> int:
    try:
        import sounddevice as sd
    except OSError as e:
        print(f"Could not load PortAudio: {e}")
        print("On WSL/Ubuntu try: sudo apt-get install -y libportaudio2 libasound2-plugins")
        return 1

    print("Default devices:", sd.default.device)
    try:
        print(sd.query_devices())
    except Exception as e:
        print(f"query_devices failed: {e}")

    buf = bytearray()
    print(f"\nRecording {seconds}s — say something…")
    try:
        with sd.RawInputStream(samplerate=rate, channels=1, dtype="int16", blocksize=blocksize) as mic:
            remaining = rate * seconds
            while remaining > 0:
                n = min(blocksize, remaining)
                data, _overflowed = mic.read(n)
                buf.extend(bytes(data))
                remaining -= n

        print("Playing it back…")
        with sd.RawOutputStream(samplerate=rate, channels=1, dtype="int16") as speaker:
            speaker.write(bytes(buf))
    except Exception as e:
        print(f"Audio I/O failed: {e}")
        print("If on WSLg, confirm `pactl info` works and PULSE_SERVER is set.")
        return 1

    print(f"Audio OK — captured {len(buf)} bytes.")
    return 0
