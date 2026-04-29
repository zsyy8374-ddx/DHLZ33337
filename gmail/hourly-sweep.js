#!/usr/bin/env node
// Hourly email sweep - searches both accounts for unread emails in last 2 hours
// Hardcoded parameters for cron use - no --account filter means all accounts
process.argv = [
  process.argv[0],
  __filename,
  '--q', 'is:unread newer_than:2h',
  '--max', '30'
];
require('./gmail-search.js');
