require('../google-dns-patch.cjs');
process.argv = [process.argv[0], process.argv[1], '--id', '19da26fd029ab7ac', '--account', 'hello@dongshi.me'];
require('./gmail-mark-read.js');
