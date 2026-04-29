#!/usr/bin/env node
// Wrapper: apply DNS patch then run gmail-search with forwarded args
require('../google-dns-patch.cjs');
// Rewrite argv so gmail-search sees itself as the main script
process.argv[1] = require('path').join(__dirname, 'gmail-search.js');
require('./gmail-search.js');
