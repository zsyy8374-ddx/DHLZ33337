#!/usr/bin/env node
require('../google-dns-patch.cjs');
process.argv = [process.argv[0], process.argv[1], '--account', 'hello@dongshi.me', '--id', '19dba01386e8465e'];
require('./gmail-mark-read.js');
