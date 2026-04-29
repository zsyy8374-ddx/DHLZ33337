// Wrapper: search hello@dongshi.me for unread in last 2h
process.argv.push('--q', 'is:unread newer_than:2h', '--max', '20', '--account', 'hello@dongshi.me');
require('./gmail-search.js');
