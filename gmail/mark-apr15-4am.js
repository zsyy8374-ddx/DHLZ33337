// Mark apr15 4am newsletters as read - tries all tokens for account
require('../google-dns-patch.cjs');

const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

const toMark = [
  { id: '19d90ce7343afffd', account: 'hello@dongshi.me' },  // Bloomberg Technology newsletter
  { id: '19d90afa1f3503c7', account: 'hello@dongshi.me' },  // Evolving AI Insights newsletter
];

async function buildClient(tokenObj) {
  const secretPath = path.resolve(__dirname, '../secrets/gcal/client_secret.json');
  const raw = JSON.parse(fs.readFileSync(secretPath, 'utf8'));
  const cfg = raw.installed || raw.web;
  const redirectUri = 'http://127.0.0.1:53682/oauth2callback';
  const oauth2 = new google.auth.OAuth2(cfg.client_id, cfg.client_secret, redirectUri);
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

async function markReadWithAnyToken(tokens, id, account) {
  const matching = tokens.filter(t => (t.authorizedEmailAddress || '').toLowerCase() === account.toLowerCase());
  for (const tokenObj of matching) {
    try {
      const gmail = await buildClient(tokenObj);
      await gmail.users.messages.modify({
        userId: 'me',
        id,
        requestBody: { removeLabelIds: ['UNREAD'] }
      });
      console.log(`✓ Marked read: ${id} (${account}) via ${path.basename(tokenObj.file)}`);
      return true;
    } catch (e) {
      console.log(`  ↳ Token ${path.basename(tokenObj.file)} failed: ${e.message}`);
    }
  }
  console.error(`✗ All tokens failed for ${id} (${account})`);
  return false;
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
    await markReadWithAnyToken(allTokens, id, account);
  }
}

main();
