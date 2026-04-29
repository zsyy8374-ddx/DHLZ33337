// Wrapper: apply DNS patch then run gmail-search for recent unread emails
require('../google-dns-patch.cjs');

// Inject args before requiring gmail-search
process.argv.push('--q', 'is:unread newer_than:2h', '--max', '20');

require('./gmail-search.js');
