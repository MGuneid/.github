#!/usr/bin/env bash
# ============================================
# GitHub Repository Secrets Setup Script
# ============================================
# This script reads your .env file and sets each
# variable as a GitHub repository secret using the gh CLI.
#
# Prerequisites:
#   - gh CLI installed and authenticated
#   - .env file in the project root with your credentials
#
# Usage:
#   ./scripts/setup-github-secrets.sh [repo]
#
# Example:
#   ./scripts/setup-github-secrets.sh mguneid/.github
# ============================================

set -euo pipefail

REPO="${1:-}"
ENV_FILE="${2:-.env}"

if [[ -z "$REPO" ]]; then
    echo "Usage: $0 <owner/repo> [.env file path]"
    echo "Example: $0 mguneid/.github"
    exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: $ENV_FILE not found."
    echo "Copy .env.example to .env and fill in your values first:"
    echo "  cp .env.example .env"
    exit 1
fi

echo "Setting GitHub secrets for repo: $REPO"
echo "Reading from: $ENV_FILE"
echo ""

count=0
while IFS= read -r line; do
    # Skip comments and empty lines
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue

    key="${line%%=*}"
    value="${line#*=}"

    # Skip lines without = or with empty keys
    [[ -z "$key" || "$key" == "$line" ]] && continue

    # Trim whitespace
    key="$(echo "$key" | xargs)"
    value="$(echo "$value" | xargs)"

    # Skip placeholder values
    if [[ "$value" == *"XXXXXXXXXXXX"* ]]; then
        echo "SKIP: $key (still has placeholder value)"
        continue
    fi

    echo "SET:  $key"
    echo "$value" | gh secret set "$key" --repo "$REPO"
    ((count++))
done < "$ENV_FILE"

echo ""
echo "Done. $count secrets set for $REPO."
