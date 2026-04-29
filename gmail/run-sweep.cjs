require('../google-dns-patch.cjs');
const { execFileSync } = require('child_process');
const path = require('path');

const account = process.argv[2] || 'hello@dongshi.me';
const result = require('./gmail-search.js');
