#!/bin/bash
cd /Users/openclaw/.openclaw/workspace
node --require ./google-dns-patch.cjs gmail/gmail-search.js --q "is:unread newer_than:2h" --max 20 --account "$1" 2>/dev/null
