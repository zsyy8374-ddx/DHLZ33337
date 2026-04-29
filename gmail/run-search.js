// Wrapper: loads DNS patch then runs gmail-search with preset args
process.chdir('/Users/openclaw/.openclaw/workspace');
require('../google-dns-patch.cjs');

// Inject argv before loading the search script
// We'll just run it directly — pass args via process.argv
const [,, ...args] = process.argv;
process.argv = [process.argv[0], process.argv[1], ...args];

require('./gmail-search.js');
