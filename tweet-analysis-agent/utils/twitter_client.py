"""Twitter/X client using the web GraphQL API (browse like a human).

This uses Twitter's public web bearer token + guest token to fetch tweets
the same way a browser does - no API credits needed.

Also supports official API v2 (tweepy) as fallback if you have credits.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Optional

import httpx

from models.schemas import RawTweet

# Twitter web app's public bearer token (embedded in their JS, used by every browser)
WEB_BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
GRAPHQL_QID = "V3vfsYzNEyD9tsf4xoFRgw"  # TweetResultByRestId
GRAPHQL_FEATURES = {
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}

TIMEOUT = httpx.Timeout(20.0)


def extract_tweet_id(url: str) -> Optional[str]:
    """Extract tweet ID from a Twitter/X URL."""
    match = re.search(r"/status/(\d+)", url)
    return match.group(1) if match else None


class TwitterWebClient:
    """Fetch tweets using Twitter's web GraphQL API (like a browser)."""

    def __init__(self):
        self._guest_token: str | None = None
        self._headers = {
            "Authorization": f"Bearer {WEB_BEARER}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "en",
        }

    def _ensure_guest_token(self) -> None:
        """Get a guest token if we don't have one."""
        if self._guest_token:
            return
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                "https://api.twitter.com/1.1/guest/activate.json",
                headers=self._headers,
            )
            resp.raise_for_status()
            self._guest_token = resp.json()["guest_token"]
            self._headers["x-guest-token"] = self._guest_token

    def _refresh_guest_token(self) -> None:
        """Force refresh the guest token."""
        self._guest_token = None
        if "x-guest-token" in self._headers:
            del self._headers["x-guest-token"]
        self._ensure_guest_token()

    def get_tweet(self, tweet_id: str) -> Optional[RawTweet]:
        """Fetch a single tweet by ID using the web GraphQL API."""
        self._ensure_guest_token()

        variables = json.dumps({
            "tweetId": tweet_id,
            "withCommunity": False,
            "includePromotedContent": False,
            "withVoice": False,
        })

        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(
                f"https://x.com/i/api/graphql/{GRAPHQL_QID}/TweetResultByRestId",
                params={
                    "variables": variables,
                    "features": json.dumps(GRAPHQL_FEATURES),
                },
                headers=self._headers,
            )

            # If guest token expired, refresh and retry once
            if resp.status_code in (401, 403):
                self._refresh_guest_token()
                resp = client.get(
                    f"https://x.com/i/api/graphql/{GRAPHQL_QID}/TweetResultByRestId",
                    params={
                        "variables": variables,
                        "features": json.dumps(GRAPHQL_FEATURES),
                    },
                    headers=self._headers,
                )

            if resp.status_code != 200:
                return None

            data = resp.json()
            tweet_result = data.get("data", {}).get("tweetResult", {}).get("result", {})

            # Handle tombstone (deleted/suspended tweets)
            if tweet_result.get("__typename") == "TweetTombstone":
                return None

            legacy = tweet_result.get("legacy", {})
            user_result = tweet_result.get("core", {}).get("user_results", {}).get("result", {})
            user_legacy = user_result.get("legacy", {})

            if not legacy.get("full_text"):
                return None

            # Extract metrics
            metrics = {
                "like_count": legacy.get("favorite_count", 0),
                "retweet_count": legacy.get("retweet_count", 0),
                "reply_count": legacy.get("reply_count", 0),
                "quote_count": legacy.get("quote_count", 0),
                "bookmark_count": legacy.get("bookmark_count", 0),
            }

            # Extract media URLs
            media_urls = []
            for media in legacy.get("extended_entities", {}).get("media", []):
                if media.get("media_url_https"):
                    media_urls.append(media["media_url_https"])

            username = user_legacy.get("screen_name", "unknown")

            return RawTweet(
                tweet_id=tweet_id,
                author_username=username,
                author_name=user_legacy.get("name", ""),
                text=legacy["full_text"],
                created_at=legacy.get("created_at", ""),
                url=f"https://x.com/{username}/status/{tweet_id}",
                metrics=metrics,
                media=media_urls,
                referenced_tweets=[],
                fetched_via="twitter_web",
            )

    def get_tweets_batch(self, tweet_ids: list[str], delay: float = 0.5) -> list[RawTweet]:
        """Fetch multiple tweets with rate limiting."""
        results = []
        for i, tid in enumerate(tweet_ids):
            tweet = self.get_tweet(tid)
            if tweet:
                results.append(tweet)
            if i < len(tweet_ids) - 1:
                time.sleep(delay)
        return results


# --- Singleton web client ---
_web_client: TwitterWebClient | None = None


def _get_web_client() -> TwitterWebClient:
    global _web_client
    if _web_client is None:
        _web_client = TwitterWebClient()
    return _web_client


def get_tweet(tweet_id: str) -> Optional[RawTweet]:
    """Fetch a single tweet (web API, no credits needed)."""
    return _get_web_client().get_tweet(tweet_id)


def get_tweets_batch(tweet_ids: list[str]) -> list[RawTweet]:
    """Fetch multiple tweets (web API, no credits needed)."""
    return _get_web_client().get_tweets_batch(tweet_ids)


def get_bookmarks(user_id: str | None = None) -> list[RawTweet]:
    """Fetch bookmarks. Requires OAuth (official API with credits).
    Falls back to empty list if no credentials."""
    try:
        import tweepy

        client = tweepy.Client(
            consumer_key=os.environ.get("TWITTER_API_KEY", ""),
            consumer_secret=os.environ.get("TWITTER_API_SECRET", ""),
            access_token=os.environ.get("TWITTER_ACCESS_TOKEN", ""),
            access_token_secret=os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", ""),
            wait_on_rate_limit=True,
        )
        uid = user_id or os.environ.get("TWITTER_USER_ID", "")
        if not uid:
            me = client.get_me()
            uid = str(me.data.id) if me.data else ""
        if not uid:
            return []

        results = []
        pagination_token = None
        while True:
            resp = client.get_bookmarks(
                id=uid,
                tweet_fields=["created_at", "public_metrics"],
                user_fields=["username", "name"],
                expansions=["author_id"],
                max_results=100,
                pagination_token=pagination_token,
            )
            if resp.data:
                users = {u.id: u for u in (resp.includes or {}).get("users", [])}
                for tweet in resp.data:
                    author = users.get(tweet.author_id)
                    results.append(RawTweet(
                        tweet_id=str(tweet.id),
                        author_username=author.username if author else "unknown",
                        author_name=author.name if author else "",
                        text=tweet.text or "",
                        created_at=tweet.created_at.isoformat() if tweet.created_at else None,
                        url=f"https://x.com/{author.username if author else 'unknown'}/status/{tweet.id}",
                        metrics=dict(tweet.public_metrics) if tweet.public_metrics else {},
                        fetched_via="twitter_api_bookmarks",
                    ))
            if resp.meta and resp.meta.get("next_token"):
                pagination_token = resp.meta["next_token"]
                time.sleep(1)
            else:
                break
        return results
    except Exception as e:
        print(f"  [WARN] Bookmark fetch failed (needs API credits): {e}")
        return []
