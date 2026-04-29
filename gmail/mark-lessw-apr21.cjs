// Mark LessWrong newsletter as read - Apr 21 1am sweep
process.argv = ['node', 'gmail-mark-read.js', '--account', 'hello@dongshi.me', '--id', '19daef34ea949ed3'];
require('../google-dns-patch.cjs');
require('./gmail-mark-read.js');
