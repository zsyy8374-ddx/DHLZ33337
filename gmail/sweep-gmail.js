require('../google-dns-patch.cjs');

process.argv = [
  process.argv[0],
  process.argv[1],
  '--q', 'is:unread newer_than:2h',
  '--max', '20',
  '--account', 'tes.grands.yeux@gmail.com'
];

require('./gmail-search.js');
