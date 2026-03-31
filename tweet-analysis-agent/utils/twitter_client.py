"""Twitter/X API v2 client using tweepy.

Supports:
- Bearer token for app-context endpoints (tweet lookup)
- OAuth 1.0a for user-context endpoints (bookmarks)
- Batch tweet fetching with rate limit handling
"""

from __future__ import annotations

import os
import re
import time
from typing import Optional

import tweepy

from models.schemas import RawTweet


def _get_bearer_client() -> tweepy.Client:
    token = os.environ.get("TWITTER_BEARER_TOKEN", "")
    if not token:
        raise RuntimeError("TWITTER_BEARER_TOKEN not set")
    return tweepy.Client(bearer_token=token, wait_on_rate_limit=True)


def _get_oauth_client() -> tweepy.Client:
    return tweepy.Client(
        consumer_key=os.environ.get("TWITTER_API_KEY", ""),
        consumer_secret=os.environ.get("TWITTER_API_SECRET", ""),
        access_token=os.environ.get("TWITTER_ACCESS_TOKEN", ""),
        access_token_secret=os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", ""),
        wait_on_rate_limit=True,
    )


TWEET_FIELDS = ["created_at", "public_metrics", "entities", "referenced_tweets", "attachments"]
USER_FIELDS = ["username", "name"]
EXPANSIONS = ["author_id", "attachments.media_keys"]
MEDIA_FIELDS = ["url", "preview_image_url", "type"]


def extract_tweet_id(url: str) -> Optional[str]:
    """Extract tweet ID from a Twitter/X URL."""
    match = re.search(r"/status/(\d+)", url)
    return match.group(1) if match else None


def _tweet_to_raw(tweet: tweepy.Tweet, includes: dict, url: str = "", fetched_via: str = "twitter_api") -> RawTweet:
    """Convert tweepy Tweet to our RawTweet model."""
    users = {u.id: u for u in (includes.get("users") or [])}
    author = users.get(tweet.author_id)

    media_urls = []
    if includes.get("media"):
        for m in includes["media"]:
            if hasattr(m, "url") and m.url:
                media_urls.append(m.url)
            elif hasattr(m, "preview_image_url") and m.preview_image_url:
                media_urls.append(m.preview_image_url)

    tweet_url = url or f"https://x.com/{author.username if author else 'unknown'}/status/{tweet.id}"

    return RawTweet(
        tweet_id=str(tweet.id),
        author_username=author.username if author else "unknown",
        author_name=author.name if author else "",
        text=tweet.text or "",
        created_at=tweet.created_at.isoformat() if tweet.created_at else None,
        url=tweet_url,
        metrics=dict(tweet.public_metrics) if tweet.public_metrics else {},
        media=media_urls,
        referenced_tweets=[{"type": r.type, "id": str(r.id)} for r in (tweet.referenced_tweets or [])],
        fetched_via=fetched_via,
    )


def get_tweet(tweet_id: str) -> Optional[RawTweet]:
    """Fetch a single tweet by ID."""
    client = _get_bearer_client()
    resp = client.get_tweet(
        tweet_id,
        tweet_fields=TWEET_FIELDS,
        user_fields=USER_FIELDS,
        expansions=EXPANSIONS,
        media_fields=MEDIA_FIELDS,
    )
    if resp.data is None:
        return None
    return _tweet_to_raw(resp.data, resp.includes or {})


def get_tweets_batch(tweet_ids: list[str]) -> list[RawTweet]:
    """Batch fetch tweets (up to 100 per request)."""
    client = _get_bearer_client()
    results = []

    # Twitter API allows max 100 IDs per request
    for i in range(0, len(tweet_ids), 100):
        batch = tweet_ids[i : i + 100]
        resp = client.get_tweets(
            batch,
            tweet_fields=TWEET_FIELDS,
            user_fields=USER_FIELDS,
            expansions=EXPANSIONS,
            media_fields=MEDIA_FIELDS,
        )
        if resp.data:
            includes = resp.includes or {}
            for tweet in resp.data:
                results.append(_tweet_to_raw(tweet, includes))

        if i + 100 < len(tweet_ids):
            time.sleep(1)  # Be kind to rate limits

    return results


def get_bookmarks(user_id: str | None = None) -> list[RawTweet]:
    """Fetch all bookmarks for the authenticated user. Requires OAuth 1.0a."""
    client = _get_oauth_client()
    uid = user_id or os.environ.get("TWITTER_USER_ID", "")
    if not uid:
        me = client.get_me()
        if me.data:
            uid = str(me.data.id)
        else:
            raise RuntimeError("Could not determine user ID. Set TWITTER_USER_ID in .env")

    results = []
    pagination_token = None

    while True:
        resp = client.get_bookmarks(
            id=uid,
            tweet_fields=TWEET_FIELDS,
            user_fields=USER_FIELDS,
            expansions=EXPANSIONS,
            media_fields=MEDIA_FIELDS,
            max_results=100,
            pagination_token=pagination_token,
        )
        if resp.data:
            includes = resp.includes or {}
            for tweet in resp.data:
                results.append(_tweet_to_raw(tweet, includes, fetched_via="twitter_api_bookmarks"))

        if resp.meta and resp.meta.get("next_token"):
            pagination_token = resp.meta["next_token"]
            time.sleep(1)
        else:
            break

    return results
