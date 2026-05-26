"""Local mic/speaker I/O for the Live session.

Gemini Live expects: input 16-bit PCM, 16 kHz, mono; output 16-bit PCM, 24 kHz, mono.
On WSLg this routes through the WSLg PulseAudio server. `sounddevice` (PortAudio) is the
default backend; if PortAudio can't reach PulseAudio on your machine, see README for the
`soundcard` fallback.

Importing this module imports sounddevice (and thus needs libportaudio); the CLI only
imports it for the `review` command, so `list`/`brief` work without audio libs.
"""

from __future__ import annotations

import asyncio
import queue
import threading

import sounddevice as sd

INPUT_RATE = 16000
OUTPUT_RATE = 24000
CHANNELS = 1
DTYPE = "int16"
BLOCKSIZE = 1600  # 100 ms at 16 kHz


class Microphone:
    """Captures mic audio and pushes raw PCM byte chunks onto an asyncio queue."""

    def __init__(self, loop: asyncio.AbstractEventLoop, out_queue: "asyncio.Queue[bytes]"):
        self._loop = loop
        self._queue = out_queue
        self._stream = sd.RawInputStream(
            samplerate=INPUT_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=BLOCKSIZE,
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status):  # runs on PortAudio thread
        self._loop.call_soon_threadsafe(self._queue.put_nowait, bytes(indata))

    def __enter__(self) -> "Microphone":
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stream.stop()
        self._stream.close()


class Speaker:
    """Plays raw PCM byte chunks via a background thread so writes don't block the loop."""

    def __init__(self):
        self._queue: "queue.Queue[bytes | None]" = queue.Queue()
        self._stream = sd.RawOutputStream(samplerate=OUTPUT_RATE, channels=CHANNELS, dtype=DTYPE)
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while True:
            chunk = self._queue.get()
            if chunk is None:
                break
            self._stream.write(chunk)

    def play(self, chunk: bytes) -> None:
        self._queue.put(chunk)

    def __enter__(self) -> "Speaker":
        self._stream.start()
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._queue.put(None)
        self._thread.join(timeout=2)
        self._stream.stop()
        self._stream.close()
