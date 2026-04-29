// Mark Ollama newsletter email as read
require('../google-dns-patch.cjs');
process.argv = [process.argv[0], process.argv[1], '--id', '19d81f7d049695ea', '--account', 'hello@dongshi.me'];
require('./gmail-mark-read.js');
