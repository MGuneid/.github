"""Report Generator Agent - Produces findings.json and summary.md.

Combines parsed tweets, verified claims, and tested strategies into
a structured report consumable by downstream agent teams.
"""

from __future__ import annotations

from models.schemas import (
    Category,
    Claim,
    Evidence,
    Finding,
    ParsedTweet,
    Report,
    RiskLevel,
    Sentiment,
    Statistics,
    Strategy,
    StrategyStatus,
    TestedStrategy,
    Tool,
    Verdict,
    VerifiedClaim,
)


def _build_finding(
    tweet: ParsedTweet,
    verified_entry: dict | None,
    tested_entry: dict | None,
) -> Finding:
    """Build a Finding from parsed tweet + verification + testing data."""
    # Reconstruct verified claims
    verified_claims = []
    if verified_entry:
        for vc_data in verified_entry.get("verified_claims", []):
            try:
                verified_claims.append(VerifiedClaim(
                    original=Claim(**vc_data["original"]),
                    verdict=Verdict(vc_data.get("verdict", "unverifiable")),
                    confidence=vc_data.get("confidence", 0.0),
                    evidence=[Evidence(**e) for e in vc_data.get("evidence", [])],
                    reasoning=vc_data.get("reasoning", ""),
                ))
            except (KeyError, ValueError):
                pass

    # Reconstruct tested strategies
    tested_strategies = []
    if tested_entry:
        for ts_data in tested_entry.get("tested_strategies", []):
            try:
                tested_strategies.append(TestedStrategy(
                    original=Strategy(**ts_data["original"]),
                    status=StrategyStatus(ts_data.get("status", "unknown")),
                    risk_level=RiskLevel(ts_data.get("risk_level", "medium")),
                    checks_performed=ts_data.get("checks_performed", []),
                    findings=ts_data.get("findings", []),
                    scam_indicators=ts_data.get("scam_indicators", []),
                ))
            except (KeyError, ValueError):
                pass

    # Determine if actionable
    actionable = False
    if verified_claims:
        has_verified = any(vc.verdict == Verdict.VERIFIED and vc.confidence >= 0.7 for vc in verified_claims)
        actionable = has_verified
    if tested_strategies:
        has_viable = any(ts.status == StrategyStatus.VIABLE for ts in tested_strategies)
        actionable = actionable or has_viable

    # Build summary
    summary_parts = []
    if verified_claims:
        v_count = sum(1 for vc in verified_claims if vc.verdict == Verdict.VERIFIED)
        d_count = sum(1 for vc in verified_claims if vc.verdict == Verdict.DEBUNKED)
        summary_parts.append(f"{v_count} verified, {d_count} debunked claims")
    if tested_strategies:
        viable = sum(1 for ts in tested_strategies if ts.status == StrategyStatus.VIABLE)
        risky = sum(1 for ts in tested_strategies if ts.status in (StrategyStatus.RISKY, StrategyStatus.SCAM))
        summary_parts.append(f"{viable} viable, {risky} risky strategies")
    summary = ". ".join(summary_parts) if summary_parts else "No claims or strategies extracted."

    return Finding(
        tweet_id=tweet.tweet_id,
        author=tweet.author_username,
        url=tweet.url,
        category=tweet.category,
        sentiment=tweet.sentiment,
        claims=verified_claims,
        strategies=tested_strategies,
        tools=tweet.tools,
        actionable=actionable,
        summary=summary,
    )


def run_report_generator(
    parsed_tweets: list[ParsedTweet],
    verified_data: list[dict],
    tested_data: list[dict],
) -> Report:
    """Generate the final report combining all pipeline data."""
    # Index verified and tested data by tweet_id
    verified_map = {v["tweet_id"]: v for v in verified_data}
    tested_map = {t["tweet_id"]: t for t in tested_data}

    findings = []
    for tweet in parsed_tweets:
        finding = _build_finding(
            tweet,
            verified_map.get(tweet.tweet_id),
            tested_map.get(tweet.tweet_id),
        )
        findings.append(finding)

    # Compute statistics
    total_claims = sum(len(f.claims) for f in findings)
    stats = Statistics(
        total_tweets=len(findings),
        total_claims=total_claims,
        verified=sum(1 for f in findings for c in f.claims if c.verdict == Verdict.VERIFIED),
        debunked=sum(1 for f in findings for c in f.claims if c.verdict == Verdict.DEBUNKED),
        partially_true=sum(1 for f in findings for c in f.claims if c.verdict == Verdict.PARTIALLY_TRUE),
        unverifiable=sum(1 for f in findings for c in f.claims if c.verdict == Verdict.UNVERIFIABLE),
        strategies_viable=sum(1 for f in findings for s in f.strategies if s.status == StrategyStatus.VIABLE),
        strategies_dead=sum(1 for f in findings for s in f.strategies if s.status == StrategyStatus.DEAD),
        strategies_risky=sum(1 for f in findings for s in f.strategies if s.status == StrategyStatus.RISKY),
        strategies_scam=sum(1 for f in findings for s in f.strategies if s.status == StrategyStatus.SCAM),
    )

    report = Report(
        meta={
            "pipeline_version": "0.1.0",
            "agents": ["ingestion", "parser", "fact_checker", "strategy_tester", "report_generator"],
            "verification_sources": [
                "dexscreener", "pumpfun", "dune", "moonshot", "solscan",
                "coingecko", "defillama", "tavily", "brave_search",
            ],
        },
        findings=findings,
        statistics=stats,
    )

    print(f"  Generated report: {stats.total_tweets} tweets, {stats.total_claims} claims")
    print(f"    Verified: {stats.verified} | Debunked: {stats.debunked} | Partial: {stats.partially_true} | Unverifiable: {stats.unverifiable}")
    print(f"    Strategies - Viable: {stats.strategies_viable} | Dead: {stats.strategies_dead} | Risky: {stats.strategies_risky} | Scam: {stats.strategies_scam}")

    return report
