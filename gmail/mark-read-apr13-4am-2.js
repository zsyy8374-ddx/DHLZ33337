// Mark commercial emails as read - Apr 13 4am sweep (newsletter)
process.argv = ['node', 'gmail-mark-read.js', '--id', '19d865618a3265e3', '--account', 'hello@dongshi.me'];
require('../google-dns-patch.cjs');
require('./gmail-mark-read.js');
