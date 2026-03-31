"""Direct analysis script - uses Claude's own analysis instead of API calls.
Run this inside Claude Code where Claude can analyze directly.
"""

import json
from pathlib import Path
from datetime import datetime

# Load raw tweets
raw = json.loads(Path("data/raw/bookmarks.json").read_text())

# ============================================================
# CLAUDE'S DIRECT ANALYSIS OF ALL 34 TWEETS
# ============================================================

findings = []

for tweet in raw:
    tid = tweet["tweet_id"]
    author = tweet["author_username"]
    text = tweet["text"]
    metrics = tweet["metrics"]
    url = tweet["url"]
    created = tweet.get("created_at", "")

    findings.append({
        "tweet_id": tid,
        "author": author,
        "url": url,
        "text": text,
        "created_at": created,
        "metrics": metrics,
        "analysis": None,  # Will be filled by Claude
    })

# Save for Claude to analyze
Path("data/raw/tweets_for_analysis.json").write_text(
    json.dumps(findings, indent=2, ensure_ascii=False)
)

print(f"Prepared {len(findings)} tweets for direct analysis")
print("Tweet authors:", ", ".join(f"@{t['author']}" for t in findings))
