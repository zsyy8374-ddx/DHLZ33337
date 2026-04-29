#!/usr/bin/env node
// One-shot script: send the LLM scan email for Friday April 24, 2026 evening
try { require('../google-dns-patch.cjs'); } catch (e) {}

const { google } = require('googleapis');
const path = require('path');
const fs = require('fs');

const ACCOUNT = 'hello@dongshi.me';
const TO = 'hello@dongshi.me';
const SUBJECT = '🧠 LLM Scan from Ludwig, Friday 2026-04-24 evening';
const BODY_FILE = '/Volumes/x10/tmp_openclaw/llm_scan_email.html';

const tokenPath = path.join(__dirname, 'tokens', `${ACCOUNT}.json`);
const tokens = JSON.parse(fs.readFileSync(tokenPath, 'utf8'));

const oauth2Client = new google.auth.OAuth2(
  process.env.GMAIL_CLIENT_ID || tokens.client_id,
  process.env.GMAIL_CLIENT_SECRET || tokens.client_secret,
  'urn:ietf:wg:oauth:2.0:oob'
);
oauth2Client.setCredentials(tokens);

const gmail = google.gmail({ version: 'v1', auth: oauth2Client });

const htmlBody = fs.readFileSync(BODY_FILE, 'utf8');

const messageParts = [
  `From: ${ACCOUNT}`,
  `To: ${TO}`,
  `Subject: ${SUBJECT}`,
  'MIME-Version: 1.0',
  'Content-Type: text/html; charset=utf-8',
  '',
  htmlBody
];

const message = messageParts.join('\n');
const encodedMessage = Buffer.from(message).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

gmail.users.messages.send({
  userId: 'me',
  requestBody: { raw: encodedMessage }
}, (err, res) => {
  if (err) {
    console.error('Error sending email:', err.message);
    process.exit(1);
  }
  console.log('Email sent! Message ID:', res.data.id);
});
