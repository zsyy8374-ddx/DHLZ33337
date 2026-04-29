// Mark Bloomberg Businessweek newsletter as read - Apr 25 4am sweep
require('../google-dns-patch.cjs');
process.argv = [
  process.argv[0], process.argv[1],
  '--id', '19dc44c3aeb9722a',
  '--account', 'hello@dongshi.me'
];
require('./gmail-mark-read.js');
