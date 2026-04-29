require('../google-dns-patch.cjs');
process.argv = ['node', 'gmail-search.js', '--q', process.env.GMAIL_QUERY || 'is:unread newer_than:2h', '--max', process.env.GMAIL_MAX || '20', '--account', process.env.GMAIL_ACCOUNT || 'tes.grands.yeux@gmail.com'];
require('./gmail-search.js');
