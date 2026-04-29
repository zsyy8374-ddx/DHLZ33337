require('../google-dns-patch.cjs');
process.argv = [process.argv[0], process.argv[1], '--id', '19dc04c4a84f5496', '--account', 'hello@dongshi.me'];
require('./gmail-mark-read.js');
