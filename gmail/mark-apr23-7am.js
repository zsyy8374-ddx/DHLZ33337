// Batch mark-as-read wrapper with DNS patch
require('../google-dns-patch.cjs');

const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

const toMark = [
  { id: '19dbab52a1d378ea', account: 'tes.grands.yeux@gmail.com' }, // Greystar survey reminder
  { id: '19dbaae72267586e', account: 'tes.grands.yeux@gmail.com' }, // Chase payment confirmation
  { id: '19dbaa71accea0fa', account: 'tes.grands.yeux@gmail.com' }, // Stanford FCU Rewards promo
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
