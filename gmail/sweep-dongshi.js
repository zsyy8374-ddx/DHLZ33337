require('../google-dns-patch.cjs');
const { execSync } = require('child_process');

// Set args before requiring gmail-search
process.argv = [
  process.argv[0],
  process.argv[1],
  '--q', 'is:unread newer_than:2h',
  '--max', '20',
  '--account', 'hello@dongshi.me'
];

require('./gmail-search.js');
