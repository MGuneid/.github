"""Pydantic models for the tweet analysis pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- Enums ---


class Category(str, Enum):
    DEFI = "defi"
    TRADING = "trading"
    ONCHAIN = "onchain"
    DEV = "dev"
    TOOLS = "tools"
    ALPHA = "alpha"
    OTHER = "other"


class Sentiment(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    EDUCATIONAL = "educational"


class Verdict(str, Enum):
    VERIFIED = "verified"
    DEBUNKED = "debunked"
    PARTIALLY_TRUE = "partially_true"
    UNVERIFIABLE = "unverifiable"


class StrategyStatus(str, Enum):
    VIABLE = "viable"
    DEAD = "dead"
    RISKY = "risky"
    SCAM = "scam"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# --- Stage 1: Raw Tweet ---


class RawTweet(BaseModel):
    tweet_id: str
    author_username: str
    author_name: str = ""
    text: str
    created_at: Optional[str] = None
    url: str
    metrics: dict = Field(default_factory=dict)
    media: list[str] = Field(default_factory=list)
    referenced_tweets: list[dict] = Field(default_factory=list)
    fetched_via: str = "twitter_api"  # twitter_api | tavily | apify | manual


# --- Stage 2: Parsed Tweet ---


class Claim(BaseModel):
    text: str
    claim_type: str = ""  # price, tvl, yield, strategy, general


class Strategy(BaseModel):
    description: str
    steps: list[str] = Field(default_factory=list)
    tokens_involved: list[str] = Field(default_factory=list)
    protocols_involved: list[str] = Field(default_factory=list)


class Tool(BaseModel):
    name: str
    url: Optional[str] = None
    description: str = ""


class ParsedTweet(BaseModel):
    tweet_id: str
    author_username: str
    text: str
    url: str
    claims: list[Claim] = Field(default_factory=list)
    strategies: list[Strategy] = Field(default_factory=list)
    tools: list[Tool] = Field(default_factory=list)
    addresses: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)
    category: Category = Category.OTHER
    sentiment: Sentiment = Sentiment.NEUTRAL


# --- Stage 3: Verified Claims ---


class Evidence(BaseModel):
    source: str  # coingecko, dexscreener, defillama, dune, solscan, pumpfun, moonshot, tavily, brave
    data: str
    url: Optional[str] = None


class VerifiedClaim(BaseModel):
    original: Claim
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)
    reasoning: str = ""


# --- Stage 4: Tested Strategies ---


class TestedStrategy(BaseModel):
    original: Strategy
    status: StrategyStatus
    risk_level: RiskLevel = RiskLevel.MEDIUM
    checks_performed: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    scam_indicators: list[str] = Field(default_factory=list)


# --- Stage 5: Final Report ---


class Finding(BaseModel):
    tweet_id: str
    author: str
    url: str
    category: Category
    sentiment: Sentiment
    claims: list[VerifiedClaim] = Field(default_factory=list)
    strategies: list[TestedStrategy] = Field(default_factory=list)
    tools: list[Tool] = Field(default_factory=list)
    actionable: bool = False
    summary: str = ""


class Statistics(BaseModel):
    total_tweets: int = 0
    total_claims: int = 0
    verified: int = 0
    debunked: int = 0
    partially_true: int = 0
    unverifiable: int = 0
    strategies_viable: int = 0
    strategies_dead: int = 0
    strategies_risky: int = 0
    strategies_scam: int = 0


class Report(BaseModel):
    meta: dict = Field(default_factory=dict)
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    findings: list[Finding] = Field(default_factory=list)
    statistics: Statistics = Field(default_factory=Statistics)
