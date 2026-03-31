"""Multi-model AI client layer.

Model hierarchy (tested & working as of 2026-03-31):
- PRIMARY: Qwen 3.6 Plus (via OpenRouter, free) - main analysis
- SECOND_OPINION: Nemotron 120B (via OpenRouter, free) - alternative perspective
- CLAUDE: (when Anthropic credits are added) - upgrades primary to Claude
- KIMI: (when Moonshot balance is topped up) - additional perspective

The fact-checker uses PRIMARY + SECOND_OPINION for consensus.
The parser uses only the PRIMARY model.
"""

from __future__ import annotations

import os
from typing import Optional

import anthropic
import httpx

TIMEOUT = httpx.Timeout(90.0)

# Tested & working free models on OpenRouter
PRIMARY_FREE_MODEL = "qwen/qwen3.6-plus-preview:free"
SECOND_FREE_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
BACKUP_FREE_MODELS = [
    "minimax/minimax-m2.5:free",
    "stepfun/step-3.5-flash:free",
    "arcee-ai/trinity-large-preview:free",
]


# --- OpenRouter ---


def call_openrouter(
    prompt: str,
    max_tokens: int = 2000,
    model: str | None = None,
) -> Optional[str]:
    """Call a model via OpenRouter."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return None

    model = model or PRIMARY_FREE_MODEL

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"    [WARN] OpenRouter ({model}) error: {e}")
        return None


# --- Anthropic (Claude) - available when credits are added ---


def call_claude(prompt: str, max_tokens: int = 2000, model: str = "claude-sonnet-4-20250514") -> Optional[str]:
    """Call Claude via Anthropic API. Returns None if no credits."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"    [WARN] Claude API error: {e}")
        return None


# --- Kimi / Moonshot AI - available when balance is topped up ---


def call_kimi(prompt: str, max_tokens: int = 2000, model: str = "moonshot-v1-8k") -> Optional[str]:
    """Call Kimi/Moonshot AI. Returns None if suspended."""
    api_key = os.environ.get("MOONSHOT_API_KEY", "")
    if not api_key:
        return None
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                "https://api.moonshot.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"    [WARN] Kimi API error: {e}")
        return None


# --- Primary call with fallback chain ---


def call_primary(prompt: str, max_tokens: int = 2000) -> str:
    """Call primary AI model with fallback chain.

    Order: Claude (if credits) → Qwen 3.6 Plus (free) → Nemotron (free) → backup models
    """
    # Try Claude first (best quality, costs money)
    result = call_claude(prompt, max_tokens)
    if result:
        return result

    # Primary free model: Qwen 3.6 Plus
    result = call_openrouter(prompt, max_tokens, model=PRIMARY_FREE_MODEL)
    if result:
        return result

    # Second free model: Nemotron 120B
    result = call_openrouter(prompt, max_tokens, model=SECOND_FREE_MODEL)
    if result:
        return result

    # Try backup free models
    for model in BACKUP_FREE_MODELS:
        result = call_openrouter(prompt, max_tokens, model=model)
        if result:
            return result

    # Last resort: Kimi
    result = call_kimi(prompt, max_tokens)
    if result:
        return result

    raise RuntimeError("All AI backends failed. Check your API keys in .env")


def call_second_opinion(prompt: str, max_tokens: int = 1000) -> dict[str, Optional[str]]:
    """Get a second opinion from a different model than primary.

    Returns {"model_name": response_or_None, ...}
    """
    opinions = {}

    # Nemotron as second opinion (different architecture than Qwen)
    opinions["nemotron_120b"] = call_openrouter(prompt, max_tokens, model=SECOND_FREE_MODEL)

    # Kimi if available
    opinions["kimi"] = call_kimi(prompt, max_tokens)

    return opinions
