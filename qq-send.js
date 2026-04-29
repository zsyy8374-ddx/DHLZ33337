#!/usr/bin/env node
/**
 * Send email via QQ Mail SMTP using nodemailer.
 *
 * Usage:
 *   node qq-send.js --to "x@y.com" --subject "Hi" --body "Hello"
 *   node qq-send.js --to "x@y.com" --subject "Hi" --bodyFile ./body.txt
 *   node qq-send.js --to "x@y.com" --subject "Hi" --bodyFile body.txt --cc "a@b.com" --bcc "c@d.com"
 *   node qq-send.js --to "x@y.com" --subject "Hi" --body "..." --html
 *   node qq-send.js --to "x@y.com" --subject "Hi" --body "..." --attachments file1.pdf,file2.png
 *
 * Config: secrets/qq/smtp.json
 */

const fs = require('fs');
const path = require('path');

// nodemailer lives in the parent workspace's node_modules (symlinked)
const nodemailer = require('nodemailer');

function arg(name, def = null) {
  const ix = process.argv.indexOf(`--${name}`);
  if (ix === -1) return def;
  return process.argv[ix + 1] ?? def;
}
function flag(name) { return process.argv.includes(`--${name}`); }
function splitList(s) {
  if (!s) return [];
  return s.split(',').map(x => x.trim()).filter(Boolean);
}

async function main() {
  const cfgPath = path.resolve(__dirname, 'secrets/qq/smtp.json');
  if (!fs.existsSync(cfgPath)) {
    console.error(`Missing SMTP config: ${cfgPath}`);
    process.exit(2);
  }
  const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));

  const to = arg('to');
  const subject = arg('subject');
  const bodyArg = arg('body');
  const bodyFile = arg('bodyFile');
  const cc = arg('cc');
  const bcc = arg('bcc');
  const replyTo = arg('replyTo');
  const fromOverride = arg('from');
  const attachments = splitList(arg('attachments'));
  const isHtml = flag('html');

  if (!to || !subject || (!bodyArg && !bodyFile)) {
    console.error('Required: --to <addr> --subject <s> (--body <text> | --bodyFile <path>)');
    process.exit(2);
  }

  let body;
  if (bodyFile) {
    body = fs.readFileSync(path.resolve(bodyFile), 'utf8');
  } else {
    body = bodyArg;
  }

  const transporter = nodemailer.createTransport({
    host: cfg.host || 'smtp.qq.com',
    port: cfg.port || 465,
    secure: cfg.secure !== false,
    auth: { user: cfg.user, pass: cfg.pass },
  });

  const message = {
    from: fromOverride || cfg.from || cfg.user,
    to,
    subject,
    [isHtml ? 'html' : 'text']: body,
  };
  if (cc) message.cc = cc;
  if (bcc) message.bcc = bcc;
  if (replyTo) message.replyTo = replyTo;
  if (attachments.length) {
    message.attachments = attachments.map(p => ({ path: path.resolve(p) }));
  }

  try {
    const info = await transporter.sendMail(message);
    console.log(JSON.stringify({
      ok: true,
      from: message.from,
      to,
      messageId: info.messageId,
      response: info.response,
      accepted: info.accepted,
      rejected: info.rejected,
    }, null, 2));
  } catch (err) {
    console.error(JSON.stringify({
      ok: false,
      error: err.message,
      code: err.code,
      response: err.response,
    }, null, 2));
    process.exit(1);
  }
}

main();
