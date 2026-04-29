require('../google-dns-patch.cjs');
const { google } = require('googleapis');
const { getAuthClient } = require('./gmail-auth.js');

async function main() {
  const auth = await getAuthClient('hello@dongshi.me');
  const gmail = google.gmail({ version: 'v1', auth });
  await gmail.users.messages.modify({
    userId: 'me',
    id: '19dc972ae60e714a',
    requestBody: { removeLabelIds: ['UNREAD'] }
  });
  console.log('Marked as read: Bloomberg Businessweek Apr 26 4am');
}
main().catch(console.error);
