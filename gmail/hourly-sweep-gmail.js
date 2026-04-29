process.argv = ['node', 'gmail-search.js', '--q', 'is:unread newer_than:2h', '--max', '20', '--account', 'tes.grands.yeux@gmail.com'];
require('../google-dns-patch.cjs');
require('./gmail-search.js');
