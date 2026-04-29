require('../google-dns-patch.cjs');

const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

const toMark = [
  { id: '19d81597f08b8fc9', account: 'hello@dongshi.me' },
  { id: '19d813aea26d6f58', account: 'hello@dongshi.me' },
];

async function buildClient(tokenObj) {
  const secretPath = path.resolve(__dirname, '../secrets/gcal/client_secret.json');
  const raw = JSON.parse(fs.readFileSync(secretPath, 'utf8'));
  const cfg = raw.installed || raw.web;
  const oauth2 = new google.auth.OAuth2(cfg.client_id, cfg.client_secret, 'http://127.0.0.1:53682/oauth2callback');
  oauth2.setCredentials(tokenObj.tokens);
  oauth2.on('tokens', (t) => {
    if (!t) return;
    const updated = { ...tokenObj.tokens, ...t };
    const out = { ...tokenObj, tokens: updated };
    delete out.file;
    fs.writeFileSync(tokenObj.file, JSON.stringify(out, null, 2));
  });
  return google.gmail({ version: 'v1', auth: oauth2 });
}

async function main() {
  const tokensDir = path.resolve(__dirname, 'tokens');
  const files = fs.readdirSync(tokensDir).filter(f => f.endsWith('.json'));
  const allTokens = files.map(f => {
    const full = path.join(tokensDir, f);
    const data = JSON.parse(fs.readFileSync(full, 'utf8'));
    return { file: full, ...data };
  });

  for (const { id, account } of toMark) {
    // Pick the newest non-expired token for this account
    const candidates = allTokens.filter(t => (t.authorizedEmailAddress || '').toLowerCase() === account.toLowerCase());
    const tokenObj = candidates.sort((a, b) => (b.tokens?.expiry_date || 0) - (a.tokens?.expiry_date || 0))[0];
    if (!tokenObj) { console.error(`No token for ${account}`); continue; }
    try {
      const gmail = await buildClient(tokenObj);
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
}

main();
