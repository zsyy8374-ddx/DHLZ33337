require('../google-dns-patch.cjs');
process.argv = [process.argv[0], process.argv[1], '--id', '19d7b8f6dc7e1af5', '--account', 'hello@dongshi.me'];
require('./gmail-mark-read.js');
