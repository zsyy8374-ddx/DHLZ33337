require('../google-dns-patch.cjs');
process.argv = ['node', 'gmail-search.js', '--account', 'tes.grands.yeux@gmail.com', '--q', 'is:unread newer_than:2h', '--max', '20'];
require('./gmail-search.js');
