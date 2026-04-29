// Mark Bloomberg newsletter as read - Apr 24 2026 4am sweep
process.argv.push('--id', '19dbf27a10ffd258', '--account', 'hello@dongshi.me');
require('./gmail-mark-read.js');
