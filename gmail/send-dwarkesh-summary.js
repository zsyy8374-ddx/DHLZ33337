#!/usr/bin/env node
// One-shot script: send Dwarkesh Jensen Huang summary Obsidian link
process.argv.push('--account', 'hello@dongshi.me');
process.argv.push('--to', 'hello@dongshi.me');
process.argv.push('--subject', 'New Dwarkesh Podcast Summary');
process.argv.push('--body', 'obsidian://open?vault=shidong&file=podcasts%2F2026-04-15%20-%20Dwarkesh%20-%20Jensen%20Huang%20%E2%80%93%20TPU%20competition%2C%20why%20we%20should%20sell%20chips%20to%20China%2C%20%26%20Nvidia%27s%20supply%20chain%20moat');
require('./gmail-send.js');
