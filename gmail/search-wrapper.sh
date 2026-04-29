#!/bin/bash
cd /Users/openclaw/.openclaw/workspace
node -r ./google-dns-patch.cjs gmail/gmail-search.js "$@"
