// Mark Westfield promotional email as read - Apr 16 2026
require('../google-dns-patch.cjs');
process.argv = ['node', 'gmail-mark-read.js', '--id', '19d9672e71f1e286', '--account', 'hello@dongshi.me'];
require('./gmail-mark-read.js');
