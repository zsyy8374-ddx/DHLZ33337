// Hourly sweep wrapper - hello@dongshi.me - unread last 2h
process.argv = ['node', 'gmail-search.js', '--q', 'is:unread newer_than:2h', '--max', '20', '--account', 'hello@dongshi.me'];
require('../google-dns-patch.cjs');
require('./gmail-search.js');
