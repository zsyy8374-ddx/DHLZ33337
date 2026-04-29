#!/usr/bin/env node
// LLM scan email - Friday April 24 evening
try { require('../google-dns-patch.cjs'); } catch (e) {}
process.argv.push('--account', 'hello@dongshi.me');
process.argv.push('--to', 'hello@dongshi.me');
process.argv.push('--subject', '🧠 LLM Scan from Ludwig, Friday 2026-04-24 evening');
process.argv.push('--html');
process.argv.push('--bodyFile', '/Volumes/x10/tmp_openclaw/llm_scan_email.html');
require('./gmail-send.js');
