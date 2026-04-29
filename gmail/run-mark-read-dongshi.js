require('../google-dns-patch.cjs');
process.argv = [process.argv[0], process.argv[1], '--ids', '19daa8e2d71ad439,19daa68f5ff5a830', '--account', 'hello@dongshi.me'];
require('./gmail-mark-read.js');
