require('../google-dns-patch.cjs');

const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

const toMark = [
  { id: '19d81597f08b8fc9', account: 'hello@dongshi.me' },   // Bloomberg Businessweek newsletter
  { id: '19d813aea26d6f58', account: 'hello@dongshi.me' },   // Evolving AI Insights newsletter
];

async function buildClient(account) {
  const tokensDir = path.resolve(__dirname, 'tokens');
  const files = fs.readdirSync(tokensDir).filter(f => f.endsWith('.json'));
  const tokenObj = files.map(f => JSON.parse(fs.readFileSync(path.join(tokensDir, f), 'utf8')))
    .find(t => (t.authorizedEmailAddress || '').toLowerCase() === account.toLowerCase());
  if (!tokenObj) throw new Error('No token for ' + account);

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
