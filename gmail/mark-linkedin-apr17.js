#!/usr/bin/env node
// Mark LinkedIn follow recommendation as read (tes.grands.yeux@gmail.com)
require('../google-dns-patch.cjs');
process.argv = [
  process.argv[0],
  require('path').join(__dirname, 'gmail-mark-read.js'),
  '--id', '19d9e3ec1b14e10a',
  '--account', 'tes.grands.yeux@gmail.com'
];
require('./gmail-mark-read.js');
