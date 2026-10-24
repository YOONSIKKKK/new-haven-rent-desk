"""Configuration and key loading.

The assignment requires the app to find .env in two places, in this order:
  1. the repo's own folder
  2. the folder one level above the repo (where the teaching staff keep theirs)

The only key the app needs at runtime is PORTKEY_API_KEY (or OPENAI_API_KEY if
someone runs it on their own OpenAI account). Everything else - Census data,
listings - is committed to data/ at build time precisely so no extra key is
needed to run this.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# Hard ceilings so a loop or a hostile input cannot burn the token budget.
MAX_REQUESTS_PER_RUN = 12
MAX_INPUT_TOKENS_PER_RUN = 60_000
MAX_OUTPUT_TOKENS_PER_RUN = 8_000
MAX_AD_TEXT_CHARS = 12_000


def _env_candidates() -> list[Path]:
    return [ROOT / ".env", ROOT.parent / ".env"]


def load_environment() -> Path | None:
    """Load the first .env found, repo folder first, then one level above."""
    for candidate in _env_candidates():
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return candidate
    return None


def get_api_key() -> tuple[str, str]:
    """Return (key, base_url). Prefers the course Portkey key.

    Raises a message a human can act on rather than a stack trace, because the
    most likely reader of this error is a grader with ten minutes on the clock.
    """
    load_environment()

    portkey = os.environ.get("PORTKEY_API_KEY")
    if portkey:
        return portkey, PORTKEY_BASE_URL

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        return openai_key, "https://api.openai.com/v1"

    looked = "\n".join(f"  - {p}" for p in _env_candidates())
    raise RuntimeError(
        "No API key found.\n"
        f"Looked for a .env file containing PORTKEY_API_KEY or OPENAI_API_KEY in:\n{looked}\n"
        "Copy .env.example to .env and fill in PORTKEY_API_KEY, or place the .env "
        "one folder above this repo."
    )


def key_status() -> dict:
    """Non-secret summary for the UI's setup banner. Never returns the key."""
    env_file = load_environment()
    return {
        "env_file_found": str(env_file) if env_file else None,
        "searched": [str(p) for p in _env_candidates()],
        "has_portkey_key": bool(os.environ.get("PORTKEY_API_KEY")),
        "has_openai_key": bool(os.environ.get("OPENAI_API_KEY")),
        "model": MODEL_NAME,
    }
