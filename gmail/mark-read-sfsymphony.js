require('../google-dns-patch.cjs');
process.argv = process.argv.slice(0,2).concat(['--id','19d88770a237e839','--account','hello@dongshi.me']);
require('./gmail-mark-read.js');
