// DNS patch + gmail search wrapper
require('../google-dns-patch.cjs');

// Patch process.argv for gmail-search.js
const baseArgs = process.argv.slice(0, 2);
const extraArgs = process.argv.slice(2);
process.argv = [...baseArgs, ...extraArgs];

require('./gmail-search.js');
