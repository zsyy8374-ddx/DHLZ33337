#!/bin/bash
cd /Users/openclaw/.openclaw/workspace
NODE_OPTIONS="--require /Users/openclaw/.openclaw/workspace/google-dns-patch.cjs" node gmail/gmail-search.js --q "is:unread newer_than:2h" --max 20 --account hello@dongshi.me
