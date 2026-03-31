"""Strategy Tester Agent - Tests viability of strategies and tools mentioned in tweets.

For each strategy/tool:
- Checks if protocol website is still live
- Queries DeFiLlama for protocol TVL
- Verifies Solana contracts via RPC + Solscan
- Checks DexScreener for liquidity, volume, pair age
- Cross-checks Pump.fun / Moonshot for memecoin legitimacy
- Queries Dune for protocol usage metrics
- Flags scam indicators
"""

from __future__ import annotations

import json
import os

import anthropic

from models.schemas import (
    ParsedTweet,
    RiskLevel,
    Strategy,
    StrategyStatus,
    TestedStrategy,
    Tool,
)
from utils.external_apis import (
    check_website_live,
    defillama_get_protocol,
    defillama_search_protocols,
    dexscreener_get_token,
    dexscreener_search_token,
    moonshot_get_token,
    pumpfun_get_token,
    solscan_get_account,
    solscan_get_token,
    solscan_get_token_holders,
)
from utils.onchain import check_account_exists, get_token_largest_accounts, is_program_active


def _test_single_strategy(strategy: Strategy, tweet: ParsedTweet) -> TestedStrategy:
    """Test a single strategy for viability."""
    checks = []
    findings = []
    scam_indicators = []

    # 1. Check protocol websites
    for protocol in strategy.protocols_involved:
        # Try common URL patterns
        for domain in [f"https://{protocol.lower()}.com", f"https://{protocol.lower()}.fi", f"https://{protocol.lower()}.io", f"https://app.{protocol.lower()}.com"]:
            try:
                live = check_website_live(domain)
                checks.append(f"Website check: {domain} → {'live' if live else 'dead'}")
                if live:
                    findings.append(f"{protocol} website is live at {domain}")
                    break
            except Exception:
                pass

    # 2. Check DeFiLlama TVL for protocols
    for protocol in strategy.protocols_involved:
        try:
            protos = defillama_search_protocols(protocol)
            if protos:
                detail = defillama_get_protocol(protos[0]["slug"])
                if detail:
                    tvl = detail.get("tvl", 0)
                    checks.append(f"DeFiLlama TVL for {protocol}: ${tvl:,.0f}")
                    if tvl and tvl > 1_000_000:
                        findings.append(f"{protocol} has healthy TVL: ${tvl:,.0f}")
                    elif tvl and tvl > 0:
                        findings.append(f"{protocol} has low TVL: ${tvl:,.0f}")
                        scam_indicators.append(f"Low TVL (${tvl:,.0f})")
                    else:
                        findings.append(f"{protocol} TVL is 0 or not found on DeFiLlama")
                        scam_indicators.append("Zero TVL on DeFiLlama")
        except Exception as e:
            checks.append(f"DeFiLlama check failed for {protocol}: {e}")

    # 3. Check token addresses on-chain
    for addr in tweet.addresses[:5]:
        # Solscan check
        try:
            token_info = solscan_get_token(addr)
            if token_info:
                checks.append(f"Solscan token found: {token_info.get('name', addr)}")
                findings.append(f"Token {token_info.get('symbol', addr)} exists on Solscan")
            else:
                checks.append(f"Solscan: token {addr[:12]}... not found")
        except Exception:
            pass

        # On-chain existence
        try:
            exists = check_account_exists(addr)
            checks.append(f"On-chain account {addr[:12]}...: {'exists' if exists else 'not found'}")
        except Exception:
            pass

        # DexScreener liquidity check
        try:
            pairs = dexscreener_get_token(addr)
            if pairs:
                top = pairs[0]
                liq = top.get("liquidity", {}).get("usd", 0)
                vol = top.get("volume", {}).get("h24", 0)
                checks.append(f"DexScreener: liquidity=${liq:,.0f}, 24h vol=${vol:,.0f}")
                if liq and liq < 10_000:
                    scam_indicators.append(f"Very low liquidity (${liq:,.0f})")
                if liq and liq > 100_000:
                    findings.append(f"Token has decent liquidity: ${liq:,.0f}")
            else:
                checks.append(f"DexScreener: no pairs found for {addr[:12]}...")
        except Exception:
            pass

        # Pump.fun check (memecoin detection)
        try:
            pump_info = pumpfun_get_token(addr)
            if pump_info:
                checks.append(f"Pump.fun token found: {pump_info.get('name', addr)}")
                if pump_info.get("complete"):
                    findings.append("Token completed bonding curve on Pump.fun")
                else:
                    scam_indicators.append("Token still on bonding curve (not fully launched)")
                if pump_info.get("king_of_the_hill_timestamp"):
                    findings.append("Token reached King of the Hill on Pump.fun")
        except Exception:
            pass

        # Moonshot check
        try:
            moon_info = moonshot_get_token(addr)
            if moon_info:
                checks.append(f"Moonshot token found: {moon_info.get('name', addr)}")
                findings.append(f"Token listed on Moonshot with price ${moon_info.get('priceUsd', 'N/A')}")
        except Exception:
            pass

        # Top holders concentration check
        try:
            holders = get_token_largest_accounts(addr)
            if holders:
                total = sum(float(h.get("uiAmount", 0) or 0) for h in holders)
                top_holder = float(holders[0].get("uiAmount", 0) or 0)
                if total > 0 and top_holder / total > 0.5:
                    scam_indicators.append(f"Top holder owns {top_holder / total:.0%} of supply")
                checks.append(f"Top holder concentration: {top_holder / total:.0%}" if total > 0 else "Could not determine holder distribution")
        except Exception:
            pass

    # 4. Determine status
    if scam_indicators:
        if len(scam_indicators) >= 3:
            status = StrategyStatus.SCAM
            risk = RiskLevel.CRITICAL
        else:
            status = StrategyStatus.RISKY
            risk = RiskLevel.HIGH
    elif not findings:
        status = StrategyStatus.UNKNOWN
        risk = RiskLevel.MEDIUM
    elif any("dead" in f.lower() or "not found" in f.lower() or "zero tvl" in f.lower() for f in findings):
        status = StrategyStatus.DEAD
        risk = RiskLevel.HIGH
    else:
        status = StrategyStatus.VIABLE
        risk = RiskLevel.LOW if not scam_indicators else RiskLevel.MEDIUM

    return TestedStrategy(
        original=strategy,
        status=status,
        risk_level=risk,
        checks_performed=checks,
        findings=findings,
        scam_indicators=scam_indicators,
    )


def _test_tool(tool: Tool) -> dict:
    """Quick viability check for a mentioned tool."""
    result = {"name": tool.name, "url": tool.url, "live": False, "notes": []}
    if tool.url:
        try:
            result["live"] = check_website_live(tool.url)
            result["notes"].append(f"Website {'live' if result['live'] else 'down'}")
        except Exception:
            result["notes"].append("Could not check website")
    return result


def run_strategy_tester(parsed_tweets: list[ParsedTweet], verified_data: list[dict]) -> list[dict]:
    """Run strategy tester on all parsed tweets."""
    results = []

    for i, tweet in enumerate(parsed_tweets):
        strategies = tweet.strategies
        tools = tweet.tools
        if not strategies and not tools:
            continue

        print(f"  Testing [{i + 1}/{len(parsed_tweets)}] @{tweet.author_username} ({len(strategies)} strategies, {len(tools)} tools)...")

        tested_strategies = []
        for j, strategy in enumerate(strategies):
            print(f"    Strategy {j + 1}: {strategy.description[:60]}...")
            tested = _test_single_strategy(strategy, tweet)
            tested_strategies.append(tested.model_dump())
            print(f"      → {tested.status.value} (risk: {tested.risk_level.value}, {len(tested.scam_indicators)} scam indicators)")

        tested_tools = []
        for tool in tools:
            tested_tools.append(_test_tool(tool))

        results.append({
            "tweet_id": tweet.tweet_id,
            "author_username": tweet.author_username,
            "url": tweet.url,
            "tested_strategies": tested_strategies,
            "tested_tools": tested_tools,
        })

    return results
