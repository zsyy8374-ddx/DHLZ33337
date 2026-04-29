// Mark Bloomberg Money Stuff newsletter as read - Apr 22, 2026 11am
process.argv = [process.argv[0], process.argv[1],
  '--account', 'hello@dongshi.me',
  '--id', '19db6620997949f9',
  '--action', 'markRead'
];
require('./gmail-mark-read.js');
