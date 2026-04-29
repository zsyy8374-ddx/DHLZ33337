#!/usr/bin/env node
/**
 * Download all attachments from a Gmail message.
 *
 * Usage:
 *   node gmail-download.js --id <messageId> [--account <email>] [--output <dir>]
 */

const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

function arg(name, def = null) {
  const ix = process.argv.indexOf(`--${name}`);
  if (ix === -1) return def;
  const v = process.argv[ix + 1];
  return v ?? def;
}

function loadTokens(tokensDir) {
  if (!fs.existsSync(tokensDir)) return [];
  return fs.readdirSync(tokensDir)
    .filter(f => f.endsWith('.json'))
    .map(f => {
      const full = path.join(tokensDir, f);
      const data = JSON.parse(fs.readFileSync(full, 'utf8'));
      return { file: full, ...data };
    });
}

function dedupeTokens(tokens) {
  const byAcct = new Map();
  for (const t of tokens) {
    const key = (t.authorizedEmailAddress || '').toLowerCase();
    if (!key) continue;
    const prev = byAcct.get(key);
    const tTime = Date.parse(t.createdAt || '') || 0;
    const pTime = prev ? (Date.parse(prev.createdAt || '') || 0) : -1;
    if (!prev || tTime > pTime) {
      byAcct.set(key, t);
    }
  }
  return Array.from(byAcct.values());
}

function sortTokensNewest(tokens) {
  return tokens.sort((a, b) => {
    const ta = Date.parse(a.createdAt || '') || 0;
    const tb = Date.parse(b.createdAt || '') || 0;
    if (tb !== ta) return tb - ta;
    try {
      const sa = fs.statSync(a.file).mtimeMs;
      const sb = fs.statSync(b.file).mtimeMs;
      return sb - sa;
    } catch {
      return 0;
    }
  });
}

async function buildClient(tokenObj) {
  const secretPath = path.resolve(__dirname, '../secrets/gmail/client_secret.json');
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

function collectParts(payload) {
  const stack = [payload];
  const parts = [];
  while (stack.length) {
    const part = stack.pop();
    if (!part) continue;
    parts.push(part);
    (part.parts || []).forEach(p => stack.push(p));
  }
  return parts;
}

function decodeB64Url(data = '') {
  let s = data.replace(/-/g, '+').replace(/_/g, '/');
  while (s.length % 4) s += '=';
  return Buffer.from(s, 'base64');
}

async function main() {
  const messageId = arg('id');
  if (!messageId) {
    console.error('Missing --id');
    process.exit(2);
  }
  const outputDir = path.resolve(arg('output', '.'));
  const account = arg('account');

  const tokensDir = path.resolve(__dirname, 'tokens');
  let tokens = loadTokens(tokensDir);
  if (!tokens.length) {
    console.error('No Gmail tokens found.');
    process.exit(2);
  }

  if (account) {
    tokens = tokens.filter(t => (t.authorizedEmailAddress || '').toLowerCase() === account.toLowerCase());
    if (!tokens.length) {
      console.error(`No token for account ${account}`);
      process.exit(2);
    }
    tokens = sortTokensNewest(tokens);
    tokens = [tokens[0]];
  } else {
    tokens = dedupeTokens(tokens);
  }

  const tokenObj = tokens[0];
  const gmail = await buildClient(tokenObj);
  const userId = 'me';

  const msg = await gmail.users.messages.get({ userId, id: messageId, format: 'full' });
  const payload = msg.data.payload;
  const parts = collectParts(payload);
  const attachments = parts.filter(p => p.filename && p.body && p.body.attachmentId);

  if (!attachments.length) {
    console.log(JSON.stringify({ saved: [], message: 'No attachments found.' }, null, 2));
    return;
  }

  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  const saved = [];
  for (const part of attachments) {
    const attachmentId = part.body.attachmentId;
    const filename = part.filename || 'attachment';
    const att = await gmail.users.messages.attachments.get({ userId, messageId, id: attachmentId });
    const data = att.data.data;
    const buffer = decodeB64Url(data);
    const target = path.join(outputDir, filename);
    fs.writeFileSync(target, buffer);
    saved.push({ filename, path: target, size: buffer.length });
  }

  console.log(JSON.stringify({ saved }, null, 2));
}

main().catch(err => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
