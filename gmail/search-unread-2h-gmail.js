// Search unread emails from last 2 hours for gmail account
process.argv.push('--q', 'is:unread newer_than:2h', '--max', '20', '--account', 'tes.grands.yeux@gmail.com');
require('../google-dns-patch.cjs');
require('./gmail-search.js');
