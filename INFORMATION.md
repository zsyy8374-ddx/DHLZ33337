# INFORMATION.md - Agent Knowledge

## Email Workflow
You have access to Shi's email accounts via Node.js scripts in the `gmail/` directory.

### Accounts
- `hello@dongshi.me` (Gmail OAuth)
- `tes.grands.yeux@gmail.com` (Gmail OAuth)
- `shi.dong@radixark.ai` (via MCP Gmail server if configured, but prefer the Node scripts for standard tasks)
- `1628354330@qq.com` (QQ Mail SMTP) — Shi's primary personal mailbox

### Core Scripts
- **Search (Gmail):** `node gmail/gmail-search.js --q "<query>" --max 5` (add `--body` for content)
- **Send (Gmail):** `node gmail/gmail-send.js --account "<from>" --to "<to>" --subject "<subject>" --body "<body>"` (attachments: `--attachments` plural)
- **Send (QQ):** `node qq-send.js --to "<to>" --subject "<subject>" --bodyFile <path>` — uses `secrets/qq/smtp.json`. Sends from `1628354330@qq.com`.

### Choosing the right sender
- **DEFAULT (since 2026-04-26): `1628354330@qq.com` via `qq-send.js`** — use for ALL outgoing email unless Shi says otherwise.
- **Fallback to `hello@dongshi.me`** when:
  - Recipient is on Gmail / overseas domain and deliverability matters (QQ→foreign mailboxes often hit spam)
  - Shi explicitly requests it (“用 dongshi.me 发” / “用 Gmail 发”)
  - Sending in a professional/business context where the domain matters
- Self-sends (Shi → Shi) under 3MB: no confirmation needed.
- All other recipients: show draft + wait for confirmation.

### Preferences
- **DNS Patch:** prepend `node -r ./google-dns-patch.cjs` to gmail scripts when DNS is flaky.
- **Draft Template:** `Dear [Name], ... Cheers, Shi`
- **Replies:** Read previous messages in thread to match tone. Always show draft for confirmation.
- **Gmail URLs:** Use `@` not `%40`.
- **Send file to self:** Email to `hello@dongshi.me`, check size < 3MB. No confirmation needed.

## Technical Notes
- Your workspace is `/Users/openclaw/.openclaw/workspace-dengxian`.
- Use absolute paths when possible in scripts.
- The `google-dns-patch.cjs` is available in your root workspace.
