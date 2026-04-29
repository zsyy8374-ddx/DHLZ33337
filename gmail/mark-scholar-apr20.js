require('../google-dns-patch.cjs');
process.argv = [process.argv[0], process.argv[1], '--id', '19daaf3c54664206', '--account', 'tes.grands.yeux@gmail.com'];
require('./gmail-mark-read.js');
