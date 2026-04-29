// Email sweep wrapper - loads DNS patch then runs gmail-search
require('../google-dns-patch.cjs');
// Inject args
process.argv = [
  process.argv[0],
  process.argv[1],
  '--q', 'is:unread newer_than:2h',
  '--max', '20',
  '--account', process.env.GMAIL_ACCOUNT || 'tes.grands.yeux@gmail.com'
];
require('./gmail-search.js');
