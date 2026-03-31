#!/usr/bin/env bash
# ============================================
# Local Credential Manager
# ============================================
# Manages credentials in a locally encrypted vault
# using GPG symmetric encryption.
#
# Usage:
#   ./scripts/credential-manager.sh encrypt   # Encrypt .env to .env.gpg
#   ./scripts/credential-manager.sh decrypt   # Decrypt .env.gpg to .env
#   ./scripts/credential-manager.sh view      # View decrypted contents (stdout)
#   ./scripts/credential-manager.sh edit      # Decrypt, open in editor, re-encrypt
# ============================================

set -euo pipefail

COMMAND="${1:-help}"
ENV_FILE=".env"
ENCRYPTED_FILE=".env.gpg"

encrypt() {
    if [[ ! -f "$ENV_FILE" ]]; then
        echo "Error: $ENV_FILE not found."
        exit 1
    fi
    gpg --symmetric --cipher-algo AES256 --batch --yes -o "$ENCRYPTED_FILE" "$ENV_FILE"
    echo "Encrypted $ENV_FILE -> $ENCRYPTED_FILE"
    echo ""
    echo "You can now safely delete $ENV_FILE if desired:"
    echo "  rm $ENV_FILE"
}

decrypt() {
    if [[ ! -f "$ENCRYPTED_FILE" ]]; then
        echo "Error: $ENCRYPTED_FILE not found."
        exit 1
    fi
    gpg --decrypt --batch -o "$ENV_FILE" "$ENCRYPTED_FILE"
    chmod 600 "$ENV_FILE"
    echo "Decrypted $ENCRYPTED_FILE -> $ENV_FILE"
}

view() {
    if [[ ! -f "$ENCRYPTED_FILE" ]]; then
        echo "Error: $ENCRYPTED_FILE not found."
        exit 1
    fi
    gpg --decrypt --batch "$ENCRYPTED_FILE"
}

edit() {
    local editor="${EDITOR:-vi}"
    decrypt
    "$editor" "$ENV_FILE"
    encrypt
    echo "Changes saved and re-encrypted."
}

case "$COMMAND" in
    encrypt) encrypt ;;
    decrypt) decrypt ;;
    view)    view ;;
    edit)    edit ;;
    *)
        echo "Usage: $0 {encrypt|decrypt|view|edit}"
        echo ""
        echo "  encrypt  - Encrypt .env to .env.gpg"
        echo "  decrypt  - Decrypt .env.gpg to .env"
        echo "  view     - Print decrypted contents to stdout"
        echo "  edit     - Decrypt, edit, and re-encrypt"
        ;;
esac
