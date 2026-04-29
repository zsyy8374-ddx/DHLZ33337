// Wrapper for hourly email sweep
process.argv = [
  process.argv[0], process.argv[1],
  '--q', 'is:unread newer_than:2h',
  '--max', '20',
  '--account', process.env.GMAIL_ACCOUNT || 'hello@dongshi.me'
];
require('./gmail-search.js');
