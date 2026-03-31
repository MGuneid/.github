"""Ingestion Agent - Fetches tweets from Twitter API, Tavily, or manual input.

Supports two modes:
- URL mode: Reads tweet URLs from a file, extracts IDs, fetches via Twitter API
- Bookmark mode: Fetches all bookmarks from authenticated user

Fallback chain: Twitter API → Tavily search → skip with warning
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from models.schemas import RawTweet
from utils.twitter_client import extract_tweet_id, get_bookmarks, get_tweet, get_tweets_batch


def _load_urls(input_file: str) -> list[str]:
    """Load tweet URLs from a text file (one URL per line)."""
    path = Path(input_file)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")
    urls = []
    for line in path.read_text().strip().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def _fetch_via_tavily(url: str) -> Optional[RawTweet]:
    """Fallback: use Tavily to search for tweet content."""
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return None

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        result = client.extract(urls=[url])

        if result and result.get("results"):
            content = result["results"][0].get("raw_content", "")
            if content:
                tweet_id = extract_tweet_id(url) or "unknown"
                # Try to extract username from URL
                parts = url.split("/")
                username = "unknown"
                for i, part in enumerate(parts):
                    if part in ("x.com", "twitter.com") and i + 1 < len(parts):
                        username = parts[i + 1]
                        break

                return RawTweet(
                    tweet_id=tweet_id,
                    author_username=username,
                    text=content[:2000],  # Cap at 2000 chars
                    url=url,
                    fetched_via="tavily",
                )
    except Exception as e:
        print(f"  [WARN] Tavily fallback failed for {url}: {e}")
    return None


def _fetch_via_twitter_api(urls: list[str]) -> tuple[list[RawTweet], list[str]]:
    """Fetch tweets via Twitter API. Returns (fetched, failed_urls)."""
    tweet_ids = []
    url_map = {}
    for url in urls:
        tid = extract_tweet_id(url)
        if tid:
            tweet_ids.append(tid)
            url_map[tid] = url

    if not tweet_ids:
        return [], urls

    fetched = []
    failed_urls = []

    try:
        tweets = get_tweets_batch(tweet_ids)
        fetched_ids = {t.tweet_id for t in tweets}
        for t in tweets:
            if t.tweet_id in url_map:
                t.url = url_map[t.tweet_id]
            fetched.append(t)

        for tid, url in url_map.items():
            if tid not in fetched_ids:
                failed_urls.append(url)
    except Exception as e:
        print(f"  [WARN] Twitter API batch fetch failed: {e}")
        failed_urls = urls

    return fetched, failed_urls


def run_ingestion(
    mode: str = "urls",
    input_file: str | None = None,
    limit: int | None = None,
) -> list[RawTweet]:
    """Run the ingestion agent.

    Args:
        mode: "urls" to read from file, "bookmarks" to fetch from Twitter API
        input_file: Path to file with tweet URLs (for url mode)
        limit: Max number of tweets to process
    """
    if mode == "bookmarks":
        print("  Fetching bookmarks from Twitter API...")
        tweets = get_bookmarks()
        if limit:
            tweets = tweets[:limit]
        print(f"  Fetched {len(tweets)} bookmarks")
        return tweets

    # URL mode
    input_file = input_file or "data/input/sample_urls.txt"
    urls = _load_urls(input_file)
    if limit:
        urls = urls[:limit]
    print(f"  Loaded {len(urls)} URLs from {input_file}")

    # Try Twitter API first
    print("  Attempting Twitter API batch fetch...")
    fetched, failed = _fetch_via_twitter_api(urls)
    print(f"  Twitter API: {len(fetched)} fetched, {len(failed)} failed")

    # Fallback to Tavily for failures
    if failed:
        print(f"  Trying Tavily fallback for {len(failed)} URLs...")
        for url in failed:
            tweet = _fetch_via_tavily(url)
            if tweet:
                fetched.append(tweet)
                print(f"    [OK] {url}")
            else:
                print(f"    [SKIP] {url}")

    return fetched
