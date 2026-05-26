"""Verify mic + speaker work before a voice session (the WSL2 audio risk).

Records 3 seconds from the default input, plays it back on the default output, and prints
the detected devices. Run: `python scripts/audio_smoketest.py` or `assistant audio-check`.
"""

from __future__ import annotations


def main() -> int:
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

    seconds, rate = 3, 16000
    print(f"\nRecording {seconds}s — say something…")
    try:
        rec = sd.rec(int(seconds * rate), samplerate=rate, channels=1, dtype="int16")
        sd.wait()
        print("Playing it back…")
        sd.play(rec, samplerate=rate)
        sd.wait()
    except Exception as e:
        print(f"Audio I/O failed: {e}")
        print("If on WSLg, confirm `pactl info` works and PULSE_SERVER is set.")
        return 1
    print("Audio OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
