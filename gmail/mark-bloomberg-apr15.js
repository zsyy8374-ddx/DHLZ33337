// Mark Bloomberg newsletter as read - Apr 15, 2026
process.argv = [process.argv[0], process.argv[1],
  '--account', 'hello@dongshi.me',
  '--id', '19d90a28d5b37032',
  '--action', 'markRead'
];
require('./gmail-mark-read.js');
