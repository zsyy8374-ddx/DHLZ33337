// Mark a single email as read
require('../google-dns-patch.cjs');
process.argv = [
  process.argv[0],
  process.argv[1],
  '--id', process.argv[2],
  '--account', process.argv[3]
];
require('./gmail-mark-read.js');
