"""Fact-Checker Agent - Verifies claims against 9 external sources.

Routing logic:
- Crypto price claims → CoinGecko + DexScreener
- Protocol/TVL claims → DeFiLlama + Dune
- Solana token claims → Solscan + DexScreener + Pump.fun + Moonshot
- Solana contract claims → Solscan + RPC
- Trading pair/liquidity claims → DexScreener
- General claims → Tavily + Brave dual-search

Uses Claude to synthesize multi-source evidence and assign verdicts.
"""

from __future__ import annotations

import json
import os

import anthropic

from models.schemas import Claim, Evidence, ParsedTweet, Verdict, VerifiedClaim
from utils.external_apis import (
    brave_search,
    coingecko_get_price,
    coingecko_search,
    defillama_get_protocol,
    defillama_search_protocols,
    dexscreener_get_token,
    dexscreener_search_token,
    moonshot_get_token,
    pumpfun_get_token,
    solscan_get_token,
    tavily_search,
)


def _gather_evidence_for_claim(claim: Claim, tweet: ParsedTweet) -> list[Evidence]:
    """Gather evidence from appropriate sources based on claim type."""
    evidence = []
    claim_type = claim.claim_type
    claim_text = claim.text.lower()

    # --- Price claims → CoinGecko + DexScreener ---
    if claim_type == "price" or any(w in claim_text for w in ["price", "pump", "dump", "ath", "moon", "$"]):
        for ticker in tweet.tickers[:3]:
            try:
                coins = coingecko_search(ticker)
                if coins:
                    price_data = coingecko_get_price(coins[0]["id"])
                    if price_data:
                        evidence.append(Evidence(
                            source="coingecko",
                            data=json.dumps({"ticker": ticker, "price_usd": price_data.get("usd"), "market_cap": price_data.get("usd_market_cap"), "volume_24h": price_data.get("usd_24h_vol")}),
                            url=f"https://www.coingecko.com/en/coins/{coins[0]['id']}",
                        ))
            except Exception as e:
                evidence.append(Evidence(source="coingecko", data=f"Error: {e}"))

            try:
                pairs = dexscreener_search_token(ticker)
                if pairs:
                    top = pairs[0]
                    evidence.append(Evidence(
                        source="dexscreener",
                        data=json.dumps({"ticker": ticker, "price_usd": top.get("priceUsd"), "liquidity": top.get("liquidity", {}).get("usd"), "volume_24h": top.get("volume", {}).get("h24"), "pair": top.get("pairAddress"), "dex": top.get("dexId")}),
                        url=top.get("url", ""),
                    ))
            except Exception as e:
                evidence.append(Evidence(source="dexscreener", data=f"Error: {e}"))

    # --- TVL / Protocol claims → DeFiLlama + Dune ---
    if claim_type == "tvl" or any(w in claim_text for w in ["tvl", "protocol", "liquidity pool", "apy", "yield"]):
        for protocol in tweet.tickers + [t.name for t in tweet.tools]:
            try:
                protos = defillama_search_protocols(protocol)
                if protos:
                    detail = defillama_get_protocol(protos[0]["slug"])
                    if detail:
                        evidence.append(Evidence(
                            source="defillama",
                            data=json.dumps({"name": detail.get("name"), "tvl": detail.get("tvl"), "chain": detail.get("chain"), "category": detail.get("category")}),
                            url=f"https://defillama.com/protocol/{protos[0]['slug']}",
                        ))
            except Exception as e:
                evidence.append(Evidence(source="defillama", data=f"Error: {e}"))

    # --- Solana token claims → Solscan + Pump.fun + Moonshot ---
    if claim_type in ("token", "strategy") or any(w in claim_text for w in ["solana", "sol", "spl", "raydium", "jupiter", "pump", "bonding"]):
        for addr in tweet.addresses[:3]:
            try:
                token_info = solscan_get_token(addr)
                if token_info:
                    evidence.append(Evidence(
                        source="solscan",
                        data=json.dumps({"address": addr, "name": token_info.get("name"), "symbol": token_info.get("symbol"), "supply": token_info.get("supply"), "decimals": token_info.get("decimals")}),
                        url=f"https://solscan.io/token/{addr}",
                    ))
            except Exception as e:
                evidence.append(Evidence(source="solscan", data=f"Error: {e}"))

            try:
                pump_info = pumpfun_get_token(addr)
                if pump_info:
                    evidence.append(Evidence(
                        source="pumpfun",
                        data=json.dumps({"address": addr, "name": pump_info.get("name"), "symbol": pump_info.get("symbol"), "market_cap": pump_info.get("market_cap"), "complete": pump_info.get("complete"), "king_of_the_hill": pump_info.get("king_of_the_hill_timestamp")}),
                        url=f"https://pump.fun/{addr}",
                    ))
            except Exception as e:
                evidence.append(Evidence(source="pumpfun", data=f"Error: {e}"))

            try:
                moon_info = moonshot_get_token(addr)
                if moon_info:
                    evidence.append(Evidence(
                        source="moonshot",
                        data=json.dumps({"address": addr, "name": moon_info.get("name"), "price": moon_info.get("priceUsd"), "volume": moon_info.get("volume24h")}),
                    ))
            except Exception as e:
                evidence.append(Evidence(source="moonshot", data=f"Error: {e}"))

    # --- DexScreener for trading pair / liquidity claims ---
    if claim_type == "strategy" or any(w in claim_text for w in ["pair", "liquidity", "dex", "swap", "pool"]):
        for addr in tweet.addresses[:3]:
            try:
                pairs = dexscreener_get_token(addr)
                if pairs:
                    top = pairs[0]
                    evidence.append(Evidence(
                        source="dexscreener",
                        data=json.dumps({"address": addr, "price_usd": top.get("priceUsd"), "liquidity_usd": top.get("liquidity", {}).get("usd"), "fdv": top.get("fdv"), "pair_created": top.get("pairCreatedAt"), "txns_24h": top.get("txns", {}).get("h24")}),
                        url=top.get("url", ""),
                    ))
            except Exception as e:
                evidence.append(Evidence(source="dexscreener", data=f"Error: {e}"))

    # --- General claims → Tavily + Brave ---
    if claim_type == "general" or not evidence:
        search_query = f"crypto {claim.text}"
        try:
            tavily_results = tavily_search(search_query, max_results=3)
            for r in tavily_results:
                evidence.append(Evidence(
                    source="tavily",
                    data=r.get("content", "")[:500],
                    url=r.get("url", ""),
                ))
        except Exception as e:
            evidence.append(Evidence(source="tavily", data=f"Error: {e}"))

        try:
            brave_results = brave_search(search_query, count=3)
            for r in brave_results:
                evidence.append(Evidence(
                    source="brave",
                    data=r.get("description", "")[:500],
                    url=r.get("url", ""),
                ))
        except Exception as e:
            evidence.append(Evidence(source="brave", data=f"Error: {e}"))

    return evidence


def _synthesize_verdict(client: anthropic.Anthropic, claim: Claim, evidence: list[Evidence], tweet_text: str) -> tuple[Verdict, float, str]:
    """Use Claude to synthesize evidence and determine verdict."""
    evidence_text = "\n".join(
        f"[{e.source}] {e.data}" + (f" (url: {e.url})" if e.url else "")
        for e in evidence
    )

    prompt = f"""You are a crypto fact-checker. Analyze this claim against the evidence.

CLAIM: "{claim.text}"
CLAIM TYPE: {claim.claim_type}

ORIGINAL TWEET CONTEXT: "{tweet_text[:500]}"

EVIDENCE GATHERED:
{evidence_text if evidence_text else "No evidence could be gathered."}

Based on the evidence, determine:
1. verdict: "verified" (evidence supports claim), "debunked" (evidence contradicts claim), "partially_true" (some aspects true, others not), or "unverifiable" (insufficient evidence)
2. confidence: 0.0 to 1.0
3. reasoning: Brief explanation (2-3 sentences)

Return ONLY valid JSON:
{{"verdict": "...", "confidence": 0.0, "reasoning": "..."}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    if text.startswith("json"):
        text = text[4:]

    try:
        data = json.loads(text.strip())
        try:
            verdict = Verdict(data.get("verdict", "unverifiable"))
        except ValueError:
            verdict = Verdict.UNVERIFIABLE
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
        reasoning = data.get("reasoning", "")
        return verdict, confidence, reasoning
    except (json.JSONDecodeError, KeyError):
        return Verdict.UNVERIFIABLE, 0.0, "Failed to synthesize evidence."


def run_fact_checker(parsed_tweets: list[ParsedTweet]) -> list[dict]:
    """Run fact-checker on all parsed tweets. Returns list of tweet dicts with verified claims."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set. Required for the fact-checker agent.")

    client = anthropic.Anthropic(api_key=api_key)
    results = []

    for i, tweet in enumerate(parsed_tweets):
        print(f"  Fact-checking [{i + 1}/{len(parsed_tweets)}] @{tweet.author_username} ({len(tweet.claims)} claims)...")
        verified_claims = []

        for j, claim in enumerate(tweet.claims):
            print(f"    Claim {j + 1}/{len(tweet.claims)}: {claim.text[:80]}...")

            # Gather evidence from external sources
            evidence = _gather_evidence_for_claim(claim, tweet)
            print(f"      Gathered {len(evidence)} pieces of evidence")

            # Synthesize verdict via Claude
            verdict, confidence, reasoning = _synthesize_verdict(client, claim, evidence, tweet.text)
            print(f"      → {verdict.value} (confidence: {confidence:.0%})")

            verified_claims.append(
                VerifiedClaim(
                    original=claim,
                    verdict=verdict,
                    confidence=confidence,
                    evidence=evidence,
                    reasoning=reasoning,
                ).model_dump()
            )

        results.append({
            "tweet_id": tweet.tweet_id,
            "author_username": tweet.author_username,
            "url": tweet.url,
            "verified_claims": verified_claims,
        })

    return results
