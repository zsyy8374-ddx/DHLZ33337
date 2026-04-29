// Mark Hyatt Regency email as read (commercial/transactional)
require('../google-dns-patch.cjs');
process.argv = [process.argv[0], process.argv[1], '--id', '19d95b904118ad58', '--account', 'tes.grands.yeux@gmail.com'];
require('./gmail-mark-read.js');
