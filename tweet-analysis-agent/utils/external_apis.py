"""External API clients for verification.

Clients for: DexScreener, Pump.fun, Dune, Moonshot, Solscan,
CoinGecko, DeFiLlama, Tavily, Brave Search.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

TIMEOUT = httpx.Timeout(15.0)


# --- DexScreener (free, no API key) ---


def dexscreener_search_token(query: str) -> list[dict]:
    """Search DexScreener for token pairs by name, symbol, or address."""
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.get(f"https://api.dexscreener.com/latest/dex/search?q={query}")
        resp.raise_for_status()
        return resp.json().get("pairs", [])


def dexscreener_get_pair(chain: str, pair_address: str) -> Optional[dict]:
    """Get specific pair info from DexScreener."""
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.get(f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{pair_address}")
        resp.raise_for_status()
        pairs = resp.json().get("pairs", [])
        return pairs[0] if pairs else None


def dexscreener_get_token(address: str) -> list[dict]:
    """Get all pairs for a token address."""
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.get(f"https://api.dexscreener.com/latest/dex/tokens/{address}")
        resp.raise_for_status()
        return resp.json().get("pairs", [])


# --- Pump.fun (Solana memecoins) ---


def pumpfun_get_token(mint_address: str) -> Optional[dict]:
    """Get token info from Pump.fun API."""
    with httpx.Client(timeout=TIMEOUT) as client:
        try:
            resp = client.get(f"https://frontend-api.pump.fun/coins/{mint_address}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError:
            return None


def pumpfun_search(query: str, limit: int = 10) -> list[dict]:
    """Search Pump.fun for tokens."""
    with httpx.Client(timeout=TIMEOUT) as client:
        try:
            resp = client.get(
                "https://frontend-api.pump.fun/coins",
                params={"searchTerm": query, "limit": limit, "sort": "market_cap", "order": "DESC"},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError:
            return []


# --- Moonshot ---


def moonshot_get_token(token_address: str) -> Optional[dict]:
    """Get token info from Moonshot/DEX Screener Moonshot API."""
    with httpx.Client(timeout=TIMEOUT) as client:
        try:
            resp = client.get(f"https://api.moonshot.cc/token/v1/solana/{token_address}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError:
            return None


# --- Dune Analytics ---


def dune_get_query_results(query_id: int, api_key: str | None = None) -> Optional[dict]:
    """Get results of a pre-existing Dune query."""
    key = api_key or os.environ.get("DUNE_API_KEY", "")
    if not key:
        return None
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.get(
            f"https://api.dune.com/api/v1/query/{query_id}/results",
            headers={"X-Dune-API-Key": key},
        )
        resp.raise_for_status()
        return resp.json()


def dune_search(query: str) -> list[dict]:
    """Search Dune for public dashboards/queries (free, no key)."""
    with httpx.Client(timeout=TIMEOUT) as client:
        try:
            resp = client.get(
                "https://api.dune.com/api/v1/search/queries",
                params={"q": query, "limit": 5},
            )
            resp.raise_for_status()
            return resp.json().get("queries", [])
        except httpx.HTTPStatusError:
            return []


# --- Solscan (Solana block explorer) ---


def solscan_get_token(address: str) -> Optional[dict]:
    """Get token metadata from Solscan."""
    jwt = os.environ.get("SOLSCAN_JWT_TOKEN", "")
    headers = {}
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    with httpx.Client(timeout=TIMEOUT) as client:
        try:
            resp = client.get(f"https://pro-api.solscan.io/v2.0/token/meta?address={address}", headers=headers)
            resp.raise_for_status()
            return resp.json().get("data")
        except httpx.HTTPStatusError:
            return None


def solscan_get_account(address: str) -> Optional[dict]:
    """Get account info from Solscan."""
    jwt = os.environ.get("SOLSCAN_JWT_TOKEN", "")
    headers = {}
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    with httpx.Client(timeout=TIMEOUT) as client:
        try:
            resp = client.get(f"https://pro-api.solscan.io/v2.0/account?address={address}", headers=headers)
            resp.raise_for_status()
            return resp.json().get("data")
        except httpx.HTTPStatusError:
            return None


def solscan_get_token_holders(address: str, limit: int = 10) -> list[dict]:
    """Get top holders of a token."""
    jwt = os.environ.get("SOLSCAN_JWT_TOKEN", "")
    headers = {}
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    with httpx.Client(timeout=TIMEOUT) as client:
        try:
            resp = client.get(
                f"https://pro-api.solscan.io/v2.0/token/holders?address={address}&page_size={limit}",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json().get("data", {}).get("items", [])
        except httpx.HTTPStatusError:
            return []


# --- CoinGecko (free tier) ---


def coingecko_search(query: str) -> list[dict]:
    """Search CoinGecko for a token."""
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.get(f"https://api.coingecko.com/api/v3/search?query={query}")
        resp.raise_for_status()
        return resp.json().get("coins", [])


def coingecko_get_price(coin_id: str) -> Optional[dict]:
    """Get current price data for a coin."""
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": coin_id, "vs_currencies": "usd", "include_market_cap": "true", "include_24hr_vol": "true"},
        )
        resp.raise_for_status()
        return resp.json().get(coin_id)


def coingecko_get_coin(coin_id: str) -> Optional[dict]:
    """Get detailed coin data."""
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.get(f"https://api.coingecko.com/api/v3/coins/{coin_id}")
        resp.raise_for_status()
        return resp.json()


# --- DeFiLlama (free, no key) ---


def defillama_get_protocol(slug: str) -> Optional[dict]:
    """Get protocol TVL and data from DeFiLlama."""
    with httpx.Client(timeout=TIMEOUT) as client:
        try:
            resp = client.get(f"https://api.llama.fi/protocol/{slug}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError:
            return None


def defillama_search_protocols(query: str) -> list[dict]:
    """Search DeFiLlama protocols."""
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.get("https://api.llama.fi/protocols")
        resp.raise_for_status()
        protocols = resp.json()
        query_lower = query.lower()
        return [p for p in protocols if query_lower in p.get("name", "").lower() or query_lower in p.get("slug", "").lower()][:10]


def defillama_get_yields() -> list[dict]:
    """Get all yield pools from DeFiLlama."""
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.get("https://yields.llama.fi/pools")
        resp.raise_for_status()
        return resp.json().get("data", [])


# --- Tavily (web search) ---


def tavily_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web using Tavily."""
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return []
    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    result = client.search(query=query, max_results=max_results)
    return result.get("results", [])


# --- Brave Search ---


def brave_search(query: str, count: int = 5) -> list[dict]:
    """Search using Brave Search API."""
    api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
    if not api_key:
        return []
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            params={"q": query, "count": count},
        )
        resp.raise_for_status()
        return resp.json().get("web", {}).get("results", [])


# --- Website liveness check ---


def check_website_live(url: str) -> bool:
    """Check if a website is still responding."""
    with httpx.Client(timeout=httpx.Timeout(10.0), follow_redirects=True) as client:
        try:
            resp = client.head(url)
            return resp.status_code < 400
        except (httpx.HTTPError, httpx.ConnectError):
            return False
