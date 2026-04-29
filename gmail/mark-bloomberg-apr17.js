require('../google-dns-patch.cjs');
process.argv.push('--id', '19d9ac8943a9ccd6', '--account', 'hello@dongshi.me');
require('./gmail-mark-read.js');
