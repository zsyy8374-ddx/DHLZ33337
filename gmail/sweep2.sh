#!/bin/bash
cd /Users/openclaw/.openclaw/workspace
node gmail/gmail-search.js --q "is:unread newer_than:2h" --max 20 --account tes.grands.yeux@gmail.com
