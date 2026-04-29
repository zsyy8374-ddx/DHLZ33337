#!/usr/bin/env node
/**
 * Gmail OAuth bootstrap (read-only).
 *
 * Usage:
 *   node gmail-auth.js --client <client_secret.json> --out <token.json> --loginHint <email>
 */

const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');

function arg(name) {
  const ix = process.argv.indexOf(`--${name}`);
  if (ix === -1) return null;
  return process.argv[ix + 1];
}

async function main() {
  const clientPath = arg('client');
  const outPath = arg('out');
  const loginHint = arg('loginHint');

  if (!clientPath || !outPath) {
    console.error('Missing --client or --out');
    process.exit(2);
  }

  const raw = JSON.parse(fs.readFileSync(clientPath, 'utf8'));
  const cfg = raw.installed || raw.web;
  if (!cfg) {
    console.error('Invalid client secret json: expected installed/web');
    process.exit(2);
  }

  // Use a local loopback redirect (Google no longer supports OOB for most clients).
  // We'll start a temporary localhost server to capture the auth code.
  const http = require('http');
  const redirectUri = 'http://127.0.0.1:53682/oauth2callback';
  const oauth2 = new google.auth.OAuth2(cfg.client_id, cfg.client_secret, redirectUri);

  const scopes = [
    // Read/search
    'https://www.googleapis.com/auth/gmail.readonly',
    // Modify labels, including UNREAD/READ
    'https://www.googleapis.com/auth/gmail.modify',
    // Create drafts / send mail
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.send',
  ];

  const url = oauth2.generateAuthUrl({
    access_type: 'offline',
    prompt: 'consent',
    scope: scopes,
    ...(loginHint ? { login_hint: loginHint } : {}),
  });

  console.log('\n1) Open this URL in your browser and complete the consent flow:');
  console.log(url);
  console.log(`\n2) After approving, your browser will redirect to ${redirectUri}`);
  console.log('   (You can close the tab once you see "Authorization complete".)');

  const code = await new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      try {
        const u = new URL(req.url, redirectUri);
        if (u.pathname !== '/oauth2callback') {
          res.writeHead(404); res.end('Not found');
          return;
        }
        const c = u.searchParams.get('code');
        const err = u.searchParams.get('error');
        if (err) {
          res.writeHead(400, { 'Content-Type': 'text/plain' });
          res.end(`Authorization failed: ${err}`);
          server.close();
          reject(new Error(`OAuth error: ${err}`));
          return;
        }
        if (!c) {
          res.writeHead(400, { 'Content-Type': 'text/plain' });
          res.end('Missing code');
          return;
        }
        res.writeHead(200, { 'Content-Type': 'text/plain' });
        res.end('Authorization complete. You may close this tab.');
        server.close();
        resolve(c);
      } catch (e) {
        server.close();
        reject(e);
      }
    });
    server.listen(53682, '127.0.0.1', () => {
      // Server ready
    });
    // Safety timeout
    setTimeout(() => {
      try { server.close(); } catch {}
      reject(new Error('Timed out waiting for OAuth redirect.'));
    }, 5 * 60 * 1000);
  });

  const { tokens } = await oauth2.getToken(code.trim());
  if (!tokens.refresh_token) {
    console.error('\nNo refresh_token returned. This usually means you previously authorized this client.');
    console.error('Fix: revoke access in Google Account -> Security -> Third-party access, then re-run.');
    process.exit(2);
  }

  // Validate by calling Gmail profile.
  oauth2.setCredentials(tokens);
  const gmail = google.gmail({ version: 'v1', auth: oauth2 });
  const prof = await gmail.users.getProfile({ userId: 'me' });

  const outDir = path.dirname(outPath);
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify({
    authorizedEmailAddress: prof.data.emailAddress,
    createdAt: new Date().toISOString(),
    scopes,
    tokens,
  }, null, 2));

  console.log(`\nSaved token to: ${outPath}`);
  console.log(`Authorized as: ${prof.data.emailAddress}`);
  console.log('Done.');
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
