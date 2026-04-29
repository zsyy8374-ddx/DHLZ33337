require('../google-dns-patch.cjs');
process.argv = ['node', 'gmail-mark-read.js', '--id', '19d9db7e496c978f', '--account', 'hello@dongshi.me'];
require('./gmail-mark-read.js');
