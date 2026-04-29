// Batch mark-as-read wrapper with DNS patch
require('../google-dns-patch.cjs');

const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

const toMark = [
  { id: '19d788dc88cf286d', account: 'tes.grands.yeux@gmail.com' },
  { id: '19d788d460c76904', account: 'hello@dongshi.me' },
  { id: '19d7869a733d42c5', account: 'tes.grands.yeux@gmail.com' },
];

async function buildClient(account) {
  const tokensDir = path.resolve(__dirname, 'tokens');
  // Use account-named file directly to avoid stale duplicate token files (account1.json etc)
  const tokenPath = path.join(tokensDir, account + '.json');
  if (!require('fs').existsSync(tokenPath)) throw new Error('No token file for ' + account);
  const tokenObj = JSON.parse(require('fs').readFileSync(tokenPath, 'utf8'));

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
