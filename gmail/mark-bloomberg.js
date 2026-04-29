// Mark Bloomberg newsletter as read
process.chdir('/Users/openclaw/.openclaw/workspace');
require('../google-dns-patch.cjs');

process.argv = [
  process.argv[0],
  process.argv[1],
  '--id', '19d7c3309f5aeb1e',
  '--account', 'hello@dongshi.me'
];

require('./gmail-mark-read.js');
