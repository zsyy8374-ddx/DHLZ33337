process.argv = ['node', 'gmail-mark-read.js', '--id', '19da566357e2b4c8', '--account', 'hello@dongshi.me'];
require('../google-dns-patch.cjs');
require('./gmail-mark-read.js');
