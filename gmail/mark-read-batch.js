#!/usr/bin/env node
// Batch mark-as-read for hello@dongshi.me: commercial emails from this sweep
const { execSync } = require('child_process');
require('../google-dns-patch.cjs');

const account = 'hello@dongshi.me';
const ids = [
  '19d770e958bdeaaa',
  '19d76f0239873acf',
  '19d76e8a80c23462'
];

const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

async function buildClient(tokenObj) {
  const secretPath = path.resolve(__dirname, '../secrets/gcal/client_secret.json');
  const raw = JSON.parse(fs.readFileSync(secretPath, 'utf8'));
  const cfg = raw.installed || raw.web;
  const oauth2 = new google.auth.OAuth2(cfg.client_id, cfg.client_secret, 'http://127.0.0.1:53682/oauth2callback');
  oauth2.setCredentials(tokenObj.tokens);
  return google.gmail({ version: 'v1', auth: oauth2 });
}

async function main() {
  const tokensDir = path.resolve(__dirname, 'tokens');
  const files = fs.readdirSync(tokensDir).filter(f => f.endsWith('.json'));
  const tokens = files.map(f => {
    const data = JSON.parse(fs.readFileSync(path.join(tokensDir, f), 'utf8'));
    return data;
  });
  const tok = tokens.find(t => (t.authorizedEmailAddress || '').toLowerCase() === account.toLowerCase());
  if (!tok) { console.error('No token for', account); process.exit(1); }
  const gmail = await buildClient(tok);
  for (const id of ids) {
    try {
      await gmail.users.messages.modify({
        userId: 'me',
        id,
        requestBody: { removeLabelIds: ['UNREAD'] }
      });
      console.log('Marked read:', id);
    } catch (e) {
      console.error('Error marking', id, e.message);
    }
  }
}

main();
