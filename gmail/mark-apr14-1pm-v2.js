// Mark commercial emails as read - Apr 14 1PM sweep (v2 - uses same pattern as gmail-mark-read.js)
require('../google-dns-patch.cjs');

const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

const toMark = [
  { id: '19d8d9ae88053e72', account: 'hello@dongshi.me' },        // Bloomberg newsletter
  { id: '19d8d9d8e57714f4', account: 'tes.grands.yeux@gmail.com' }, // HealthEquity marketing
];

async function buildClient(account) {
  const tokensDir = path.resolve(__dirname, 'tokens');
  let files = fs.readdirSync(tokensDir).filter(f => f.endsWith('.json'));
  
  let tokens = files.map(f => {
    const full = path.join(tokensDir, f);
    const data = JSON.parse(fs.readFileSync(full, 'utf8'));
    return { file: full, ...data };
  });

  tokens = tokens.filter(t => (t.authorizedEmailAddress || '').toLowerCase() === account.toLowerCase());
  
  if (!tokens.length) throw new Error('No token for ' + account);

  // Use the newest token
  tokens.sort((a, b) => {
    const ta = Date.parse(a.createdAt || '') || 0;
    const tb = Date.parse(b.createdAt || '') || 0;
    return tb - ta;
  });

  const tokenObj = tokens[0];
  const secretPath = path.resolve(__dirname, '../secrets/gcal/client_secret.json');
  const raw = JSON.parse(fs.readFileSync(secretPath, 'utf8'));
  const cfg = raw.installed || raw.web;
  const oauth2 = new google.auth.OAuth2(cfg.client_id, cfg.client_secret, 'http://127.0.0.1:53682/oauth2callback');
  oauth2.setCredentials(tokenObj.tokens);
  
  // Force token refresh
  const refreshed = await oauth2.refreshAccessToken();
  oauth2.setCredentials(refreshed.credentials);
  
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
      console.error(`✗ Failed ${id} (${account}): ${e.message}`);
    }
  }
  console.log('Done.');
}

main();
