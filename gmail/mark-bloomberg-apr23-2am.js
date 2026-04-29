// Mark Bloomberg Markets Daily newsletter as read - Apr 23, 2026 2am
process.argv = [process.argv[0], process.argv[1],
  '--account', 'hello@dongshi.me',
  '--id', '19db9b2186b13d0a',
  '--action', 'markRead'
];
require('./gmail-mark-read.js');
