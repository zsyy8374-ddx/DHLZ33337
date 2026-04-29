#!/usr/bin/env node
// Batch mark-as-read for hello@dongshi.me using all available tokens
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
  return { gmail: google.gmail({ version: 'v1', auth: oauth2 }), oauth2 };
}

async function main() {
  const tokensDir = path.resolve(__dirname, 'tokens');
  const files = fs.readdirSync(tokensDir).filter(f => f.endsWith('.json'));
  const allTokens = files.map(f => {
    const full = path.join(tokensDir, f);
    const data = JSON.parse(fs.readFileSync(full, 'utf8'));
    return { file: f, ...data };
  });
  const matchingTokens = allTokens.filter(t => (t.authorizedEmailAddress || '').toLowerCase() === account.toLowerCase());
  console.log('Matching token files:', matchingTokens.map(t => t.file));
  
  for (const tok of matchingTokens) {
    try {
      const { gmail, oauth2 } = await buildClient(tok);
      // Try refreshing credentials first
      const { credentials } = await oauth2.refreshAccessToken();
      oauth2.setCredentials(credentials);
      console.log('Token refreshed for', tok.file);
      
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
      break; // success with this token
    } catch (e) {
      console.error('Token', tok.file, 'failed:', e.message);
    }
  }
}

main();
