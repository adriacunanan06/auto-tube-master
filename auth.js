const { google } = require('googleapis');
const http = require('http');
const url = require('url');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

const SCOPES = ['https://www.googleapis.com/auth/youtube'];
const TOKEN_PATH = path.join(__dirname, 'youtube-token.json');

async function authorize() {
  console.log('==============================================');
  console.log('🔐 YouTube OAuth 2.0 Setup');
  console.log('==============================================\n');

  if (!process.env.YOUTUBE_CLIENT_ID || !process.env.YOUTUBE_CLIENT_SECRET) {
      console.error('❌ Missing YOUTUBE_CLIENT_ID or YOUTUBE_CLIENT_SECRET in .env file.');
      console.error('Please create OAuth credentials in Google Cloud Console first.');
      process.exit(1);
  }

  const oauth2Client = new google.auth.OAuth2(
    process.env.YOUTUBE_CLIENT_ID,
    process.env.YOUTUBE_CLIENT_SECRET,
    process.env.YOUTUBE_REDIRECT_URI || 'http://localhost:3000/oauth2callback'
  );

  // Generate auth url
  const authUrl = oauth2Client.generateAuthUrl({
    access_type: 'offline', // Requests a refresh token
    scope: SCOPES,
    prompt: 'consent' // Forces Google to always return a refresh token
  });

  console.log('🌐 Please open the following URL in your browser:');
  console.log('\n' + authUrl + '\n');
  console.log('Waiting for authorization code on localhost:3000...');

  // Start a local server to receive the callback
  const server = http.createServer(async (req, res) => {
    try {
      const q = url.parse(req.url, true).query;
      
      if (q.error) {
        console.error('❌ Error returned from Google:', q.error);
        res.end('Error authenticating. You can close this tab and check the console.');
        server.close();
        process.exit(1);
      }

      if (q.code) {
        res.end('Authentication successful! You can close this tab and return to the terminal.');
        server.close();

        console.log('\n✅ Received authorization code! Exchanging for tokens...');
        
        const { tokens } = await oauth2Client.getToken(q.code);
        oauth2Client.setCredentials(tokens);

        fs.writeFileSync(TOKEN_PATH, JSON.stringify(tokens, null, 2));
        console.log(`\n🎉 Success! Credentials saved to ${TOKEN_PATH}`);
        console.log(`Your Auto-Tube script is now fully authorized to upload to your YouTube channel!`);
        console.log(`You never have to run this script again.`);
        process.exit(0);
      }
    } catch (e) {
      console.error('❌ Error during token exchange:', e.message);
      res.end('Error during token exchange. Check terminal.');
      server.close();
      process.exit(1);
    }
  });

  server.listen(3000, () => {
      // Local server listening
  });
}

authorize();
