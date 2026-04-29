// Search recent unread emails for tes.grands.yeux@gmail.com
process.argv = [process.argv[0], process.argv[1], '--q', 'is:unread newer_than:2h', '--max', '20', '--account', 'tes.grands.yeux@gmail.com'];
require('../google-dns-patch.cjs');
require('./gmail-search.js');
