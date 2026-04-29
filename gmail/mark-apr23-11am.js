// Mark commercial emails as read - Apr 23, 11:44 AM sweep
require('../google-dns-patch.cjs');

const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

const toMark = [
  { id: '19dbb8d06b30d888', account: 'hello@dongshi.me' }, // Stanford Park Hotel
  { id: '19dbb88adc834eb5', account: 'hello@dongshi.me' }, // Bloomberg Businessweek
  { id: '19dbb8766ca05876', account: 'hello@dongshi.me' }, // Notion Team
  { id: '19dbb7d9509c0f51', account: 'hello@dongshi.me' }, // Matt Levine Money Stuff
];

async function buildClient(account) {
  const tokensDir = path.resolve(__dirname, 'tokens');
  const tokenPath = path.join(tokensDir, account + '.json');
  if (!fs.existsSync(tokenPath)) throw new Error('No token file for ' + account);
  const tokenObj = JSON.parse(fs.readFileSync(tokenPath, 'utf8'));
  const secretPath = path.resolve(__dirname, '../secrets/gcal/client_secret.json');
  const raw = JSON.parse(fs.readFileSync(secretPath, 'utf8'));
  const cfg = raw.installed || raw.web;
  const oauth2 = new google.auth.OAuth2(cfg.client_id, cfg.client_secret, 'http://127.0.0.1:53682/oauth2callback');
  oauth2.setCredentials(tokenObj.tokens);
  return google.gmail({ version: 'v1', auth: oauth2 });
}

async function main() {
  for (const { id, account } of toMark) {
    try {
      const gmail = await buildClient(account);
      await gmail.users.messages.modify({
        userId: 'me',
        id,
        requestBody: { removeLabelIds: ['UNREAD'] }
      });
      console.log(`✓ Marked read: ${id} (${account})`);
    } catch (e) {
      console.error(`✗ Failed ${id}: ${e.message}`);
    }
  }
}

main();
