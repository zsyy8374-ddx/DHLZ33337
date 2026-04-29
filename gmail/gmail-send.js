#!/usr/bin/env node
/**
 * Send an email via Gmail API using stored OAuth tokens.
 *
 * Usage:
 *   node gmail/gmail-send.js --account hello@dongshi.me --to "a@b.com" --subject "Hi" --body "Hello"
 *   node gmail/gmail-send.js --account tes.grands.yeux@gmail.com --to "a@b.com" --subject "Hi" --bodyFile ./body.txt
 *   node gmail/gmail-send.js --account ... --to ... --subject ... --body ... --cc "x@y.com" --bcc "z@y.com" --replyTo "noreply@..."
 *   node gmail/gmail-send.js --account ... --to ... --subject ... --body ... --attachments file1.pdf,file2.png
 *
 * Tokens are expected at: gmail/tokens/*.json (created by gmail-auth.js)
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

function flag(name) {
  return process.argv.includes(`--${name}`);
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

function b64UrlEncode(buf) {
  return Buffer.from(buf)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
}

function rfc2047encode(str) {
  // Minimal: only encode if non-ascii
  if (/^[\x00-\x7F]*$/.test(str)) return str;
  const b64 = Buffer.from(str, 'utf8').toString('base64');
  return `=?UTF-8?B?${b64}?=`;
}

function buildRawEmail({ from, to, cc, bcc, replyTo, subject, bodyText, isHtml, attachments }) {
  const boundary = `----=_openclaw_${Date.now()}_${Math.random().toString(16).slice(2)}`;

  const headers = [];
  headers.push(`From: ${from}`);
  headers.push(`To: ${to}`);
  if (cc) headers.push(`Cc: ${cc}`);
  if (bcc) headers.push(`Bcc: ${bcc}`);
  if (replyTo) headers.push(`Reply-To: ${replyTo}`);
  headers.push(`Subject: ${rfc2047encode(subject || '')}`);
  headers.push('MIME-Version: 1.0');

  const contentType = isHtml ? 'text/html; charset="UTF-8"' : 'text/plain; charset="UTF-8"';

  if (!attachments || attachments.length === 0) {
    headers.push(`Content-Type: ${contentType}`);
    headers.push('Content-Transfer-Encoding: 7bit');
    return headers.join('\r\n') + '\r\n\r\n' + (bodyText || '') + '\r\n';
  }

  headers.push(`Content-Type: multipart/mixed; boundary="${boundary}"`);

  const parts = [];
  // text/html part
  parts.push(
    `--${boundary}\r\n` +
    `Content-Type: ${contentType}\r\n` +
    'Content-Transfer-Encoding: 7bit\r\n\r\n' +
    (bodyText || '') + '\r\n'
  );

  for (const filePath of attachments) {
    const filename = path.basename(filePath);
    const data = fs.readFileSync(filePath);
    const contentType = 'application/octet-stream';
    const b64 = data.toString('base64');

    parts.push(
      `--${boundary}\r\n` +
      `Content-Type: ${contentType}; name="${filename}"\r\n` +
      'Content-Transfer-Encoding: base64\r\n' +
      `Content-Disposition: attachment; filename="${filename}"\r\n\r\n` +
      b64.replace(/(.{76})/g, '$1\r\n') + '\r\n'
    );
  }

  parts.push(`--${boundary}--\r\n`);

  return headers.join('\r\n') + '\r\n\r\n' + parts.join('');
}

async function main() {
  // Validate that no unknown flags are passed
  const KNOWN_FLAGS = new Set(['account','to','subject','body','bodyFile','cc','bcc','replyTo','attachments','html']);
  const unknownFlags = process.argv.slice(2)
    .filter(a => a.startsWith('--'))
    .map(a => a.slice(2))
    .filter(f => !KNOWN_FLAGS.has(f));
  if (unknownFlags.length) {
    console.error(`Unknown flag(s): ${unknownFlags.map(f => '--' + f).join(', ')}`);
    console.error(`Known flags: ${[...KNOWN_FLAGS].map(f => '--' + f).join(', ')}`);
    process.exit(2);
  }

  const account = arg('account');
  const to = arg('to');
  const subject = arg('subject', '');
  const body = arg('body');
  const bodyFile = arg('bodyFile');
  const cc = arg('cc');
  const bcc = arg('bcc');
  const replyTo = arg('replyTo');
  const attachments = splitList(arg('attachments'));
  const isHtml = flag('html');

  if (!account) {
    console.error('Missing --account');
    process.exit(2);
  }
  if (!to) {
    console.error('Missing --to');
    process.exit(2);
  }
  if (!body && !bodyFile) {
    console.error('Missing --body or --bodyFile');
    process.exit(2);
  }

  const tokensDir = path.resolve(__dirname, 'tokens');
  let tokens = loadTokens(tokensDir);
  tokens = tokens.filter(t => (t.authorizedEmailAddress || '').toLowerCase() === account.toLowerCase());
  if (!tokens.length) {
    console.error(`No token matching --account ${account} in ${tokensDir}`);
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
  const tokenObj = tokens[0];

  const gmail = await buildClient(tokenObj);
  const userId = 'me';

  const bodyText = bodyFile ? fs.readFileSync(path.resolve(bodyFile), 'utf8') : body?.replace(/\\n/g, '\n');

  const rawEmail = buildRawEmail({
    from: tokenObj.authorizedEmailAddress,
    to,
    cc,
    bcc,
    replyTo,
    subject,
    bodyText,
    isHtml,
    attachments: attachments.map(p => path.resolve(p)),
  });

  const res = await gmail.users.messages.send({
    userId,
    requestBody: {
      raw: b64UrlEncode(rawEmail),
    },
  });

  const id = res?.data?.id;
  const threadId = res?.data?.threadId;

  process.stdout.write(JSON.stringify({
    ok: true,
    account: tokenObj.authorizedEmailAddress,
    id,
    threadId,
    permalink: id ? `https://mail.google.com/mail/u/${encodeURIComponent(tokenObj.authorizedEmailAddress)}/#sent/${id}` : null,
  }, null, 2));
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
