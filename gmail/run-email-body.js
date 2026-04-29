#!/usr/bin/env node
require('../google-dns-patch.cjs');
process.argv.push('--body');
require('./gmail-search.js');
