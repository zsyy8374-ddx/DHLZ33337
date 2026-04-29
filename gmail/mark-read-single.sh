#!/bin/zsh
cd /Users/openclaw/.openclaw/workspace
node -r ./google-dns-patch.cjs gmail/gmail-mark-read.js --id "$1" --account "$2"
