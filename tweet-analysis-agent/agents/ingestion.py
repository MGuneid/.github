"""Ingestion Agent - Fetches tweets from Tavily search, Twitter API, or manual input.

Supports two modes:
- URL mode: Reads tweet URLs from a file, fetches content
- Bookmark mode: Fetches all bookmarks from authenticated Twitter user

Fallback chain: Twitter web browsing → Tavily search → Brave search → skip
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from models.schemas import RawTweet
from utils.twitter_client import extract_tweet_id, get_bookmarks, get_tweets_batch


def _load_urls(input_file: str) -> list[str]:
    """Load tweet URLs from a text file (one URL per line)."""
    path = Path(input_file)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")
    urls = []
    for line in path.read_text().strip().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            # Clean URL - remove tracking params
            clean = re.split(r"[?&]s=", line)[0]
            urls.append(clean)
    return urls


def _extract_username(url: str) -> str:
    """Extract username from a Twitter/X URL."""
    parts = url.split("/")
    for i, part in enumerate(parts):
        if part in ("x.com", "twitter.com") and i + 1 < len(parts):
            return parts[i + 1]
    return "unknown"


def _fetch_via_tavily_search(url: str) -> Optional[RawTweet]:
    """Fetch tweet content via Tavily search (works when extract/API are blocked)."""
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return None

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        tweet_id = extract_tweet_id(url) or "unknown"
        username = _extract_username(url)

        # Search for the specific tweet
        result = client.search(
            query=f"site:x.com {username} {tweet_id}",
            max_results=1,
            include_raw_content=True,
        )

        if result and result.get("results"):
            r = result["results"][0]
            # Prefer raw_content (full text), fall back to content (snippet)
            content = r.get("raw_content") or r.get("content", "")
            title = r.get("title", "")

            # Combine title + content for maximum info
            full_text = f"{title}\n\n{content}" if title and title not in content else content

            if full_text.strip():
                return RawTweet(
                    tweet_id=tweet_id,
                    author_username=username,
                    text=full_text[:3000],
                    url=url,
                    fetched_via="tavily_search",
                )
    except Exception as e:
        print(f"    [WARN] Tavily search failed for {url}: {e}")
    return None


def _fetch_via_brave_search(url: str) -> Optional[RawTweet]:
    """Fetch tweet content via Brave Search as last resort."""
    from utils.external_apis import brave_search

    tweet_id = extract_tweet_id(url) or "unknown"
    username = _extract_username(url)

    try:
        results = brave_search(f"site:x.com {username} {tweet_id}", count=1)
        if results:
            r = results[0]
            content = r.get("description", "")
            title = r.get("title", "")
            full_text = f"{title}\n\n{content}" if title else content

            if full_text.strip():
                return RawTweet(
                    tweet_id=tweet_id,
                    author_username=username,
                    text=full_text[:3000],
                    url=url,
                    fetched_via="brave_search",
                )
    except Exception as e:
        print(f"    [WARN] Brave search failed for {url}: {e}")
    return None


def _fetch_via_twitter_web(urls: list[str]) -> tuple[list[RawTweet], list[str]]:
    """Fetch tweets via Twitter web browsing (GraphQL + guest token). No credits needed."""
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
        print(f"  [WARN] Twitter web fetch failed: {e}")
        failed_urls = list(url_map.values())

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

    # Fetch via Twitter web browsing (like a human, no credits needed)
    print("  Fetching via Twitter web browsing...")
    fetched, failed = _fetch_via_twitter_web(urls)
    if fetched:
        print(f"  Twitter web: {len(fetched)} fetched, {len(failed)} remaining")
    else:
        print(f"  Twitter web failed, using search fallback for all {len(failed)} URLs")

    # Fallback to Tavily search for failures
    still_failed = []
    if failed:
        print(f"  Fetching via Tavily search...")
        for url in failed:
            tweet = _fetch_via_tavily_search(url)
            if tweet:
                fetched.append(tweet)
                print(f"    [OK] @{tweet.author_username}: {tweet.text[:80]}...")
            else:
                still_failed.append(url)

    # Last resort: Brave search
    if still_failed:
        print(f"  Trying Brave search for {len(still_failed)} remaining URLs...")
        for url in still_failed:
            tweet = _fetch_via_brave_search(url)
            if tweet:
                fetched.append(tweet)
                print(f"    [OK] @{tweet.author_username}: {tweet.text[:80]}...")
            else:
                print(f"    [SKIP] {url}")

    return fetched
