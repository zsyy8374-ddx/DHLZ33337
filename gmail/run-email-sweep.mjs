import { createRequire } from 'module';
const require = createRequire(import.meta.url);

// Apply DNS patch
require('../google-dns-patch.cjs');

// Now run the gmail search
const { execFileSync } = require('child_process');
const args = process.argv.slice(2);
const result = execFileSync('node', ['gmail/gmail-search.js', ...args], {
  cwd: '/Users/openclaw/.openclaw/workspace',
  env: { ...process.env, NODE_OPTIONS: '--require /Users/openclaw/.openclaw/workspace/google-dns-patch.cjs' },
  encoding: 'utf8'
});
process.stdout.write(result);
