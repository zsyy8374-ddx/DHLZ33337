require('../google-dns-patch.cjs');
const ids = process.env.MSG_IDS.split(',');
const account = process.env.ACCOUNT;
process.argv = ['node', 'gmail-mark-read.js', '--account', account, '--ids', ...ids];
require('./gmail-mark-read.js');
