#!/usr/bin/env node
// Wrapper: DNS patch + sweep hello@dongshi.me for unread in last 2h
require('../google-dns-patch.cjs');
process.argv = [
  process.argv[0],
  require('path').join(__dirname, 'gmail-search.js'),
  '--q', 'is:unread newer_than:2h',
  '--max', '20',
  '--account', 'hello@dongshi.me'
];
require('./gmail-search.js');
