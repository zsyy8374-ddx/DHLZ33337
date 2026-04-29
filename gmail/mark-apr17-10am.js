// Batch mark-as-read - Apr 17 10am sweep
require('../google-dns-patch.cjs');

const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

const toMark = [
  { id: '19d9c656fbdb80fe', account: 'tes.grands.yeux@gmail.com' }, // Stanford FCU marketing
  { id: '19d9c3ac9f4e2599', account: 'hello@dongshi.me' },           // Bloomberg newsletter
  { id: '19d9c5d148773b46', account: 'hello@dongshi.me' },           // Cometeer delivery
];

async function buildClient(account) {
  const tokensDir = path.resolve(__dirname, 'tokens');
  // Use the account-named token file directly to avoid stale duplicates
  const tokenPath = path.join(tokensDir, account + '.json');
  if (!fs.existsSync(tokenPath)) throw new Error('No token file for ' + account);
  const tokenObj = JSON.parse(fs.readFileSync(tokenPath, 'utf8'));

  const secretPath = path.resolve(__dirname, '../secrets/gcal/client_secret.json');
  const raw = JSON.parse(fs.readFileSync(secretPath, 'utf8'));
  const cfg = raw.installed || raw.web;
  const oauth2 = new google.auth.OAuth2(cfg.client_id, cfg.client_secret, 'http://127.0.0.1:53682/oauth2callback');
  oauth2.setCredentials(tokenObj.tokens);
  // persist refreshed tokens
  oauth2.on('tokens', (t) => {
    if (!t) return;
    const updated = { ...tokenObj, tokens: { ...tokenObj.tokens, ...t } };
    fs.writeFileSync(tokenPath, JSON.stringify(updated, null, 2));
  });
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
