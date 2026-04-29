#!/bin/bash
cd /Users/openclaw/.openclaw/workspace
node -r ./google-dns-patch.cjs gmail/gmail-search.js --q "is:unread newer_than:2h" --max 20 --account tes.grands.yeux@gmail.com
