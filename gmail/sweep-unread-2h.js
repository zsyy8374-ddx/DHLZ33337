#!/usr/bin/env node
// Hourly sweep: search unread emails in the last 2 hours across all accounts
process.argv.push('--q', 'is:unread newer_than:2h', '--max', '20');
require('./gmail-search.js');
