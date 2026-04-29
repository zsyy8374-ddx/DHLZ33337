#!/usr/bin/env node
require('../google-dns-patch.cjs');

// Mark commercial emails as read:
// 1. Bloomberg newsletter (hello@dongshi.me)
// 2. HealthEquity marketing (tes.grands.yeux@gmail.com)

const ids = [
  { id: '19d8d9ae88053e72', account: 'hello@dongshi.me' },
  { id: '19d8d9d8e57714f4', account: 'tes.grands.yeux@gmail.com' },
];

let idx = 0;

function next() {
  if (idx >= ids.length) {
    console.log('All done.');
    return;
  }
  const { id, account } = ids[idx++];
  process.argv = [process.argv[0], process.argv[1], '--id', id, '--account', account];
  // Reset require cache for mark-read
  delete require.cache[require.resolve('./gmail-mark-read.js')];
  require('./gmail-mark-read.js');
  setTimeout(next, 2000);
}

next();
