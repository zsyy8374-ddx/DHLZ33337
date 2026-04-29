// Wrapper: search tes.grands.yeux@gmail.com for unread in last 2h
process.argv.push('--q', 'is:unread newer_than:2h', '--max', '20', '--account', 'tes.grands.yeux@gmail.com');
require('./gmail-search.js');
