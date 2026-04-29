// Mark lululemon shipping email as read - tes.grands.yeux@gmail.com
process.argv = [
  process.argv[0], process.argv[1],
  '--id', '19dbe9100c9a3297',
  '--account', 'tes.grands.yeux@gmail.com'
];
require('./gmail-mark-read.js');
