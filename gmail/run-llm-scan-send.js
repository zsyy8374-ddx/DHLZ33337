#!/usr/bin/env node
// Wrapper: inject argv then call gmail-send logic
process.argv = [
  'node',
  'gmail-send.js',
  '--account', 'hello@dongshi.me',
  '--to', 'hello@dongshi.me',
  '--subject', '🧠 LLM Scan from Ludwig, Monday 2026-04-13 evening',
  '--html',
  '--bodyFile', '/Volumes/x10/tmp_openclaw/llm_scan_email.html'
];

require('./gmail-send.js');
