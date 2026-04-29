// Mark commercial emails as read - Apr 13 4am sweep
process.argv = ['node', 'gmail-mark-read.js', '--id', '19d865159b18f04c', '--account', 'hello@dongshi.me'];
require('../google-dns-patch.cjs');
require('./gmail-mark-read.js');
