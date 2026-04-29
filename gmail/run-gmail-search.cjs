// Wrapper: loads dns patch then runs gmail-search
require('../google-dns-patch.cjs');
// re-use gmail-search as a module by injecting argv
const args = process.argv.slice(2); // already set by caller
require('./gmail-search.js');
