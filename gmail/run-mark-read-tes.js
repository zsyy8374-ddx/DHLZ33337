require('../google-dns-patch.cjs');
process.argv = [process.argv[0], process.argv[1], '--id', '19dc3f4c3928f40a', '--account', 'tes.grands.yeux@gmail.com'];
require('./gmail-mark-read.js');
