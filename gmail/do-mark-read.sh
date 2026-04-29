#!/bin/bash
cd /Users/openclaw/.openclaw/workspace
node gmail/gmail-mark-read.js --id "$1" --account "$2"
