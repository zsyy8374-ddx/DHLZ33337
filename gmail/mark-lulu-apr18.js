require('../google-dns-patch.cjs');
const { google } = require('googleapis');
const fs = require('fs');
const path = require('path');

async function buildClient(account) {
  const secretPath = path.resolve(__dirname, '../secrets/gcal/client_secret.json');
  const raw = JSON.parse(fs.readFileSync(secretPath, 'utf8'));
  const cfg = raw.installed || raw.web;
  const oauth2 = new google.auth.OAuth2(cfg.client_id, cfg.client_secret, 'http://127.0.0.1:53682/oauth2callback');
  const tokensDir = path.resolve(__dirname, 'tokens');
  const files = fs.readdirSync(tokensDir).filter(f => f.endsWith('.json'));
  for (const f of files) {
    const tok = JSON.parse(fs.readFileSync(path.join(tokensDir, f), 'utf8'));
    if (tok.email === account || tok.authorizedEmailAddress === account || f.replace('.json','') === account) {
      oauth2.setCredentials(tok.tokens);
      return google.gmail({ version: 'v1', auth: oauth2 });
    }
  }
  throw new Error('No token for ' + account);
}

async function markRead(gmail, id) {
  await gmail.users.messages.modify({
    userId: 'me',
    id,
    requestBody: { removeLabelIds: ['UNREAD'] }
  });
  console.log('Marked read:', id);
}

async function main() {
  const g1 = await buildClient('hello@dongshi.me');
  await markRead(g1, '19da272675aace0e'); // lululemon account updated
  await markRead(g1, '19da26fd029ab7ac'); // lululemon account activated

  const g2 = await buildClient('tes.grands.yeux@gmail.com');
  await markRead(g2, '19da27258888e263'); // lululemon order confirmation

  console.log('Done');
}

main().catch(e => { console.error(e.message); process.exit(1); });
