// Mark commercial newsletters as read - Apr 22, 2026 ~3:44 AM sweep
require('../google-dns-patch.cjs');
const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

async function buildClient(account) {
  const secretPath = path.resolve(__dirname, '../secrets/gcal/client_secret.json');
  const raw = JSON.parse(fs.readFileSync(secretPath, 'utf8'));
  const cfg = raw.installed || raw.web;
  const oauth2 = new google.auth.OAuth2(cfg.client_id, cfg.client_secret, 'http://127.0.0.1:53682/oauth2callback');
  const tokensDir = path.resolve(__dirname, 'tokens');
  const files = fs.readdirSync(tokensDir).filter(f => f.endsWith('.json'));
  const tokens = files
    .map(f => JSON.parse(fs.readFileSync(path.join(tokensDir, f), 'utf8')))
    .filter(t => (t.authorizedEmailAddress || '').toLowerCase() === account.toLowerCase())
    .sort((a, b) => Date.parse(b.createdAt || 0) - Date.parse(a.createdAt || 0));
  if (!tokens.length) throw new Error(`No token for ${account}`);
  oauth2.setCredentials(tokens[0].tokens);
  return google.gmail({ version: 'v1', auth: oauth2 });
}

async function main() {
  const toMark = [
    { account: 'hello@dongshi.me', id: '19db4b9c76a3eb7f', subject: 'Bloomberg Markets Daily: A memory stock supercycle' },
    { account: 'hello@dongshi.me', id: '19db4b3f2f1c65f6', subject: 'Evolving AI Insights: ChatGPT Introduces Images 2.0' },
  ];

  for (const item of toMark) {
    try {
      const gmail = await buildClient(item.account);
      await gmail.users.messages.batchModify({
        userId: 'me',
        ids: [item.id],
        removeLabelIds: ['UNREAD'],
      });
      console.log(`✓ Marked read: [${item.account}] ${item.subject}`);
    } catch (e) {
      console.error(`✗ Failed: ${item.subject} — ${e.message}`);
    }
  }
}

main().catch(console.error);
