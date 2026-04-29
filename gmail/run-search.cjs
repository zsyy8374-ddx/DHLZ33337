// Wrapper that applies DNS patch then runs gmail-search
require('../google-dns-patch.cjs');
// Re-run via the actual script
require('./gmail-search.js');
