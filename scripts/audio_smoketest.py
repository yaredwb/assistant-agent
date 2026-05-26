"""Standalone mic/speaker check. Delegates to assistant_agent.audiocheck so the logic
lives in one place. Run: `python scripts/audio_smoketest.py` or `assistant audio-check`.
"""

from assistant_agent.audiocheck import run

if __name__ == "__main__":
    raise SystemExit(run())
