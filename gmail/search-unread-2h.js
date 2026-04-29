// Search unread emails from last 2 hours for both accounts
process.argv.push('--q', 'is:unread newer_than:2h', '--max', '20', '--account', 'hello@dongshi.me');
require('../google-dns-patch.cjs');
require('./gmail-search.js');
