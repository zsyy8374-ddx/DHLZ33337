#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

function arg(name, def = null) {
  const ix = process.argv.indexOf(`--${name}`);
  if (ix === -1) return def;
  return process.argv[ix + 1] ?? def;
}

async function buildClient(tokenObj) {
  const secretPath = path.resolve(__dirname, '../secrets/gcal/client_secret.json');
  const raw = JSON.parse(fs.readFileSync(secretPath, 'utf8'));
  const cfg = raw.installed || raw.web;
  const oauth2 = new google.auth.OAuth2(cfg.client_id, cfg.client_secret, 'http://127.0.0.1:53682/oauth2callback');
  oauth2.setCredentials(tokenObj.tokens);
  return google.gmail({ version: 'v1', auth: oauth2 });
}

async function main() {
  const id = arg('id');
  const account = arg('account');
  if (!id || !account) {
    console.error('Usage: node gmail-mark-read.js --id <msgId> --account <email>');
    process.exit(1);
  }

  const tokensDir = path.resolve(__dirname, 'tokens');
  let files = fs.readdirSync(tokensDir).filter(f => f.endsWith('.json'));
  let tokens = files.map(f => {
    const full = path.join(tokensDir, f);
    const data = JSON.parse(fs.readFileSync(full, 'utf8'));
    return { file: full, ...data };
  });

  tokens = tokens.filter(t => (t.authorizedEmailAddress || '').toLowerCase() === account.toLowerCase());
  
  if (!tokens.length) {
    console.error(`No token for ${account}`);
    process.exit(1);
  }

  // Use the newest token
  tokens.sort((a, b) => {
    const ta = Date.parse(a.createdAt || '') || 0;
    const tb = Date.parse(b.createdAt || '') || 0;
    return tb - ta;
  });

  const tokenObj = tokens[0];
  const gmail = await buildClient(tokenObj);
  
  await gmail.users.messages.batchModify({
    userId: 'me',
    ids: [id],
    removeLabelIds: ['UNREAD']
  });

  console.log(`Marked ${id} as read in ${account}`);
}

main().catch(console.error);
