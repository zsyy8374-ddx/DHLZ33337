// Wrapper to run email check with DNS patch
require('../google-dns-patch.cjs');
process.argv = [process.argv[0], process.argv[1], '--account', process.env.EMAIL_ACCOUNT, '--q', process.env.EMAIL_QUERY, '--max', '20'];
require('./gmail-search.js');
