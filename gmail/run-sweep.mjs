// Temporary wrapper for email sweep
import { createRequire } from 'module';
import { fileURLToPath } from 'url';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const workspaceDir = path.join(__dirname, '..');

// Apply DNS patch
await import(path.join(workspaceDir, 'google-dns-patch.cjs'));

// Override argv for gmail-search
process.argv = [process.argv[0], process.argv[1], ...process.argv.slice(2)];

// Run search
await import(path.join(workspaceDir, 'gmail/gmail-search.js'));
