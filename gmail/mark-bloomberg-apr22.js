// Mark Bloomberg newsletter as read - Apr 22, 2026
process.argv = [process.argv[0], process.argv[1],
  '--account', 'hello@dongshi.me',
  '--id', '19db4daff304670a',
  '--action', 'markRead'
];
require('./gmail-mark-read.js');
