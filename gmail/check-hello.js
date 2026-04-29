require('../google-dns-patch.cjs');
process.argv = ['node', 'gmail-search.js', '--account', 'hello@dongshi.me', '--q', 'is:unread newer_than:2h', '--max', '20'];
require('./gmail-search.js');
