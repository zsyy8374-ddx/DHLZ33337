// Search recent unread emails for hello@dongshi.me
process.argv = [process.argv[0], process.argv[1], '--q', 'is:unread newer_than:2h', '--max', '20', '--account', 'hello@dongshi.me'];
require('../google-dns-patch.cjs');
require('./gmail-search.js');
