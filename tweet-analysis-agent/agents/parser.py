"""Parser Agent - Uses AI to dissect tweets and extract structured data.

For each tweet, extracts:
- Claims (factual assertions)
- Strategies (trading/DeFi strategies)
- Tools (products/protocols mentioned)
- Addresses (contract addresses, token tickers)
- Category and sentiment
"""

from __future__ import annotations

import json

from models.schemas import Category, Claim, ParsedTweet, RawTweet, Sentiment, Strategy, Tool
from utils.ai_clients import call_primary

PARSE_PROMPT = """Analyze this tweet from the crypto/DeFi space. Extract ALL structured information.

Tweet by @{author}:
\"\"\"{text}\"\"\"

Tweet URL: {url}

Return a JSON object with these fields:
{{
  "claims": [
    {{"text": "the factual claim being made", "claim_type": "price|tvl|yield|strategy|tool|general"}}
  ],
  "strategies": [
    {{
      "description": "what the strategy is",
      "steps": ["step 1", "step 2"],
      "tokens_involved": ["SOL", "ETH"],
      "protocols_involved": ["Raydium", "Jupiter"]
    }}
  ],
  "tools": [
    {{"name": "tool name", "url": "https://...", "description": "what it does"}}
  ],
  "addresses": ["any contract addresses or wallet addresses mentioned"],
  "tickers": ["any token tickers like $SOL, $ETH mentioned"],
  "category": "defi|trading|onchain|dev|tools|alpha|other",
  "sentiment": "bullish|bearish|neutral|educational"
}}

Rules:
- Extract EVERY factual claim, even implicit ones
- If a specific number/price is mentioned, that's a claim
- If a strategy or method is described, capture all steps
- If tools/products are mentioned, list them with URLs if available
- Be thorough - extract addresses even if partial
- For tickers, include the $ prefix removal (e.g., "$SOL" → "SOL")
- Categorize based on the PRIMARY focus of the tweet
- Return ONLY valid JSON, no markdown or explanation"""


def _parse_single_tweet(tweet: RawTweet) -> ParsedTweet:
    """Parse a single tweet using the primary AI model."""
    prompt = PARSE_PROMPT.format(
        author=tweet.author_username,
        text=tweet.text,
        url=tweet.url,
    )

    text = call_primary(prompt, max_tokens=2000)

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    if text.startswith("json"):
        text = text[4:]

    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError:
        # If model returns non-JSON, create minimal parsed result
        return ParsedTweet(
            tweet_id=tweet.tweet_id,
            author_username=tweet.author_username,
            text=tweet.text,
            url=tweet.url,
            claims=[Claim(text=tweet.text, claim_type="general")],
        )

    # Map to Pydantic models
    claims = [Claim(text=c.get("text", ""), claim_type=c.get("claim_type", "general")) for c in data.get("claims", [])]

    strategies = [
        Strategy(
            description=s.get("description", ""),
            steps=s.get("steps", []),
            tokens_involved=s.get("tokens_involved", []),
            protocols_involved=s.get("protocols_involved", []),
        )
        for s in data.get("strategies", [])
    ]

    tools = [
        Tool(name=t.get("name", ""), url=t.get("url"), description=t.get("description", ""))
        for t in data.get("tools", [])
    ]

    # Safe enum parsing
    cat_str = data.get("category", "other")
    try:
        category = Category(cat_str)
    except ValueError:
        category = Category.OTHER

    sent_str = data.get("sentiment", "neutral")
    try:
        sentiment = Sentiment(sent_str)
    except ValueError:
        sentiment = Sentiment.NEUTRAL

    return ParsedTweet(
        tweet_id=tweet.tweet_id,
        author_username=tweet.author_username,
        text=tweet.text,
        url=tweet.url,
        claims=claims,
        strategies=strategies,
        tools=tools,
        addresses=data.get("addresses", []),
        tickers=data.get("tickers", []),
        category=category,
        sentiment=sentiment,
    )


def run_parser(raw_tweets: list[RawTweet]) -> list[ParsedTweet]:
    """Run the parser agent on all raw tweets."""
    results = []

    for i, tweet in enumerate(raw_tweets):
        print(f"  Parsing [{i + 1}/{len(raw_tweets)}] @{tweet.author_username}: {tweet.text[:60]}...")
        try:
            parsed = _parse_single_tweet(tweet)
            results.append(parsed)
            print(
                f"    → {len(parsed.claims)} claims, {len(parsed.strategies)} strategies, "
                f"{len(parsed.tools)} tools, category={parsed.category}"
            )
        except Exception as e:
            print(f"    [ERROR] Failed to parse: {e}")
            # Still include with minimal data
            results.append(
                ParsedTweet(
                    tweet_id=tweet.tweet_id,
                    author_username=tweet.author_username,
                    text=tweet.text,
                    url=tweet.url,
                )
            )

    return results
