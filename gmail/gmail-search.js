#!/usr/bin/env node
/**
 * Search across one or more Gmail accounts using stored OAuth tokens.
 *
 * Examples:
 *   node gmail-search.js --q "from:foo subject:bar newer_than:7d" --max 5
 *   node gmail-search.js --q "has:attachment filename:pdf" --max 10 --account hello@dongshi.me
 *
 * Tokens are expected at: gmail/tokens/*.json (created by gmail-auth.js)
 */

// Apply Google DNS patch if available
try { require('../google-dns-patch.cjs'); } catch(e) {}

const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

function arg(name, def = null) {
  const ix = process.argv.indexOf(`--${name}`);
  if (ix === -1) return def;
  const v = process.argv[ix + 1];
  return v ?? def;
}

function flag(name) {
  return process.argv.includes(`--${name}`);
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

function decodeB64Url(s) {
  if (!s) return '';
  s = s.replace(/-/g, '+').replace(/_/g, '/');
  while (s.length % 4) s += '=';
  return Buffer.from(s, 'base64').toString('utf8');
}

function header(headers, name) {
  const h = (headers || []).find(x => (x.name || '').toLowerCase() === name.toLowerCase());
  return h ? h.value : '';
}

function getTextBody(payload) {
  // Prefer text/plain; fallback to text/html stripped.
  const stack = [payload];
  let html = '';
  while (stack.length) {
    const p = stack.pop();
    if (!p) continue;
    const mt = (p.mimeType || '').toLowerCase();
    if (mt === 'text/plain' && p.body && p.body.data) {
      return decodeB64Url(p.body.data);
    }
    if (mt === 'text/html' && p.body && p.body.data) {
      html = decodeB64Url(p.body.data);
    }
    (p.parts || []).forEach(pp => stack.push(pp));
  }
  if (html) {
    // very light strip
    return html.replace(/<style[\s\S]*?<\/style>/gi, '')
      .replace(/<script[\s\S]*?<\/script>/gi, '')
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }
  return '';
}

async function buildClient(tokenObj) {
  // client secrets stored centrally
  const secretPath = path.resolve(__dirname, '../secrets/gcal/client_secret.json');
  const raw = JSON.parse(fs.readFileSync(secretPath, 'utf8'));
  const cfg = raw.installed || raw.web;
  const redirectUri = 'http://127.0.0.1:53682/oauth2callback';
  const oauth2 = new google.auth.OAuth2(cfg.client_id, cfg.client_secret, redirectUri);
  oauth2.setCredentials(tokenObj.tokens);

  // Refresh if needed and persist updated tokens.
  // googleapis will refresh automatically; we hook token event.
  oauth2.on('tokens', (t) => {
    if (!t) return;
    const updated = { ...tokenObj.tokens, ...t };
    const out = { ...tokenObj, tokens: updated };
    // don't duplicate file field in persisted JSON
    delete out.file;
    fs.writeFileSync(tokenObj.file, JSON.stringify(out, null, 2));
  });

  return google.gmail({ version: 'v1', auth: oauth2 });
}

async function searchAccount(tokenObj, q, maxResults) {
  const gmail = await buildClient(tokenObj);
  const userId = 'me';

  const list = await gmail.users.messages.list({
    userId,
    q,
    maxResults,
  });

  const ids = (list.data.messages || []).map(m => m.id);
  const out = [];

  for (const id of ids) {
    const msg = await gmail.users.messages.get({ userId, id, format: 'full' });
    const payload = msg.data.payload;
    const headers = payload?.headers || [];

    const subject = header(headers, 'Subject');
    const from = header(headers, 'From');
    const to = header(headers, 'To');
    const date = header(headers, 'Date');

    // snippet is often enough; body is optional
    const snippet = msg.data.snippet || '';
    const body = flag('body') ? getTextBody(payload) : '';

    out.push({
      account: tokenObj.authorizedEmailAddress,
      id,
      threadId: msg.data.threadId,
      internalDateMs: msg.data.internalDate,
      date,
      from,
      to,
      subject,
      snippet,
      ...(flag('body') ? { body } : {}),
      permalink: `https://mail.google.com/mail/u/${encodeURIComponent(tokenObj.authorizedEmailAddress)}/#inbox/${id}`,
    });
  }

  return out;
}

function usage() {
  return `Usage: node gmail-search.js --q "<gmail query>" [--max <n>] [--account <email>] [--body]\n\nExamples:\n  node gmail-search.js --q "newer_than:7d" --max 5\n  node gmail-search.js --q "from:foo subject:bar" --max 10 --account hello@dongshi.me\n\nNotes:\n  - --q is required unless --help is provided.\n  - Add --body to include message bodies (slower).\n`;
}

async function main() {
  if (flag('help') || process.argv.includes('-h')) {
    process.stdout.write(usage());
    process.exit(0);
  }

  const q = arg('q');
  const max = parseInt(arg('max', '5'), 10);
  const account = arg('account');

  if (!q) {
    process.stderr.write('Missing --q\n\n' + usage());
    process.exit(2);
  }

  const tokensDir = path.resolve(__dirname, 'tokens');
  let tokens = loadTokens(tokensDir);
  if (!tokens.length) {
    console.error(`No tokens found in ${tokensDir}`);
    process.exit(2);
  }

  if (account) {
    tokens = tokens.filter(t => (t.authorizedEmailAddress || '').toLowerCase() === account.toLowerCase());
    if (!tokens.length) {
      console.error(`No token matching --account ${account}`);
      process.exit(2);
    }
    // If multiple tokens exist for the same account, use the newest.
    tokens.sort((a, b) => {
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
    tokens = [tokens[0]];
  }

  // If multiple tokens exist for the same account, keep only the newest per account.
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
  tokens = Array.from(byAcct.values());

  let results = [];
  for (const t of tokens) {
    const r = await searchAccount(t, q, max);
    results = results.concat(r);
  }

  // sort newest first if possible
  results.sort((a, b) => (parseInt(b.internalDateMs || '0', 10) - parseInt(a.internalDateMs || '0', 10)));

  process.stdout.write(JSON.stringify({
    query: q,
    maxPerAccount: max,
    accounts: tokens.map(t => t.authorizedEmailAddress),
    count: results.length,
    results,
  }, null, 2));
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
