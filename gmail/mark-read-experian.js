require('../google-dns-patch.cjs');
process.argv.push('--id', '19d871e197f1b74f', '--account', 'tes.grands.yeux@gmail.com');
require('./gmail-mark-read.js');
