"""Solana on-chain verification utilities.

Uses multiple RPC providers with failover:
Helius → dRPC → QuickNode → Alchemy
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

TIMEOUT = httpx.Timeout(15.0)


def _get_rpc_urls() -> list[str]:
    """Get list of Solana RPC URLs in failover order."""
    urls = []
    for key in ["HELIUS_RPC_URL", "DRPC_RPC_URL", "QUICKNODE_RPC_URL", "ALCHEMY_RPC_URL"]:
        val = os.environ.get(key, "")
        if val:
            urls.append(val)
    if not urls:
        urls.append("https://api.mainnet-beta.solana.com")  # Public fallback (rate limited)
    return urls


def _rpc_call(method: str, params: list[Any] | None = None) -> Optional[dict]:
    """Make a JSON-RPC call to Solana with failover across providers."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or [],
    }

    for rpc_url in _get_rpc_urls():
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.post(rpc_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if "result" in data:
                    return data["result"]
                if "error" in data:
                    continue  # Try next provider
        except (httpx.HTTPError, httpx.ConnectError):
            continue

    return None


def get_account_info(address: str) -> Optional[dict]:
    """Get account info for a Solana address."""
    return _rpc_call("getAccountInfo", [address, {"encoding": "jsonParsed"}])


def get_token_supply(mint_address: str) -> Optional[dict]:
    """Get token supply for a SPL token mint."""
    return _rpc_call("getTokenSupply", [mint_address])


def get_balance(address: str) -> Optional[int]:
    """Get SOL balance for an address (in lamports)."""
    result = _rpc_call("getBalance", [address])
    if result and "value" in result:
        return result["value"]
    return None


def get_signatures(address: str, limit: int = 10) -> list[dict]:
    """Get recent transaction signatures for an address."""
    result = _rpc_call("getSignaturesForAddress", [address, {"limit": limit}])
    return result if isinstance(result, list) else []


def is_program_active(program_address: str) -> bool:
    """Check if a Solana program/contract is still active (has recent transactions)."""
    sigs = get_signatures(program_address, limit=5)
    return len(sigs) > 0


def get_token_largest_accounts(mint_address: str) -> list[dict]:
    """Get largest token accounts for a mint (top holders)."""
    result = _rpc_call("getTokenLargestAccounts", [mint_address])
    if result and "value" in result:
        return result["value"]
    return []


def check_account_exists(address: str) -> bool:
    """Check if a Solana account exists."""
    info = get_account_info(address)
    return info is not None and info.get("value") is not None
