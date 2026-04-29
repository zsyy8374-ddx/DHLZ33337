// Email sweep wrapper - applies DNS patch then runs search
require('../google-dns-patch.cjs');

// Pass through arguments
const args = process.argv.slice(2);
// Parse args
const params = {};
for (let i = 0; i < args.length; i++) {
  if (args[i].startsWith('--')) {
    params[args[i].slice(2)] = args[i+1];
    i++;
  }
}

// Set argv for gmail-search.js compatibility
// We need to inject args that gmail-search.js expects
process.argv = ['node', 'gmail-search.js', ...args];

require('./gmail-search.js');
