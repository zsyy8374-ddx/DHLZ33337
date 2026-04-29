#!/bin/bash
cd /Users/openclaw/.openclaw/workspace
NODE_OPTIONS="--require /Users/openclaw/.openclaw/workspace/google-dns-patch.cjs" node gmail/gmail-mark-read.js --id "$1" --account "$2"
