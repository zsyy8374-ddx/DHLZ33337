#!/usr/bin/env node
// Wrapper: mark Cometeer email as read
process.argv.push('--id', '19d82bf5db4d33cb', '--account', 'hello@dongshi.me');
require('./gmail-mark-read.js');
