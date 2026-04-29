#!/usr/bin/env node
/**
 * Sweep recent unread emails from both accounts (last 2h).
 * Query is read from GMAIL_QUERY env var to avoid shell-quoting issues.
 */

// Apply Google DNS patch if available
try { require('../google-dns-patch.cjs'); } catch(e) {}

const query = process.env.GMAIL_QUERY || 'is:unread newer_than:2h';
const maxResults = parseInt(process.env.GMAIL_MAX || '20', 10);
const account = process.env.GMAIL_ACCOUNT || null;

// Inject args so gmail-search.js parses them
const args = [process.argv[0], process.argv[1], '--q', query, '--max', String(maxResults)];
if (account) args.push('--account', account);
process.argv = args;

require('./gmail-search.js');
