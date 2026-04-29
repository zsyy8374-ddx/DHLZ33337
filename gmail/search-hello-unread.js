// Pre-configured: search hello@dongshi.me for unread in last 2h
process.argv.push('--account', 'hello@dongshi.me', '--q', 'is:unread newer_than:2h', '--max', '20');
require('./gmail-search.js');
