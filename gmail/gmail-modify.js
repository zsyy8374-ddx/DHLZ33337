#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

function arg(name, def = null) {
  const ix = process.argv.indexOf(`--${name}`);
  if (ix === -1) return def;
  const v = process.argv[ix + 1];
  return v ?? def;
}

function splitList(s) {
  if (!s) return [];
  return s.split(',').map(x => x.trim()).filter(Boolean);
}

function loadTokens(tokensDir) {
  if (!fs.existsSync(tokensDir)) return [];
  const files = fs.readdirSync(tokensDir).filter(f => f.endsWith('.json'));
  return files.map(f => {
    const full = path.join(tokensDir, f);
    const data = JSON.parse(fs.readFileSync(full, 'utf8'));
    return { file: full, ...data };
  });
}

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

async function modifyMessages(tokenObj, ids, removeLabels, addLabels) {
  const gmail = await buildClient(tokenObj);
  const userId = 'me';

  if (!ids.length) return { ok: true, count: 0 };

  const body = {
    ids,
    addLabelIds: addLabels,
    removeLabelIds: removeLabels,
  };

  const res = await gmail.users.messages.batchModify({ userId, requestBody: body });
  
  return { 
      ok: res.status === 204,
      count: ids.length,
      status: res.status 
  };
}

async function main() {
  const account = arg('account');
  const ids = splitList(arg('ids'));
  const removeLabels = splitList(arg('remove', 'UNREAD'));
  const addLabels = splitList(arg('add'));

  if (!account) {
    console.error('Missing --account');
    process.exit(2);
  }
  if (!ids.length) {
    console.error('Missing --ids');
    process.exit(2);
  }

  const tokensDir = path.resolve(__dirname, 'tokens');
  let tokens = loadTokens(tokensDir);
  tokens = tokens.filter(t => (t.authorizedEmailAddress || '').toLowerCase() === account.toLowerCase());
  if (!tokens.length) {
    console.error(`No token matching --account ${account} in ${tokensDir}`);
    process.exit(2);
  }

  tokens.sort((a, b) => Date.parse(b.createdAt || '') - Date.parse(a.createdAt || ''));
  const tokenObj = tokens[0];

  const res = await modifyMessages(tokenObj, ids, removeLabels, addLabels);

  process.stdout.write(JSON.stringify({
    ...res,
    account: tokenObj.authorizedEmailAddress,
    ids: ids,
  }, null, 2));
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});