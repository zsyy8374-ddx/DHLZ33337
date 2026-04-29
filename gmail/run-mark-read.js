require('../google-dns-patch.cjs');
process.argv = [process.argv[0], process.argv[1], '--id', '19dc67241b0ad8f5', '--account', 'tes.grands.yeux@gmail.com'];
require('./gmail-mark-read.js');
