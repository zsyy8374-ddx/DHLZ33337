// Pre-configured: search tes.grands.yeux@gmail.com for unread in last 2h
process.argv.push('--account', 'tes.grands.yeux@gmail.com', '--q', 'is:unread newer_than:2h', '--max', '20');
require('./gmail-search.js');
