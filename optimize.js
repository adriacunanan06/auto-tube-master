const { google } = require('googleapis');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

const TOKEN_PATH = path.join(__dirname, 'youtube-token.json');

async function optimizeChannel() {
  console.log('==============================================');
  console.log('⚙️ Optimizing YouTube Channel Settings...');
  console.log('==============================================\n');

  if (!fs.existsSync(TOKEN_PATH)) {
      console.error('❌ No youtube-token.json found! You must run `node auth.js` first.');
      return;
  }

  try {
    const oauth2Client = new google.auth.OAuth2(
      process.env.YOUTUBE_CLIENT_ID,
      process.env.YOUTUBE_CLIENT_SECRET,
      process.env.YOUTUBE_REDIRECT_URI || 'http://localhost:3000/oauth2callback'
    );

    const token = JSON.parse(fs.readFileSync(TOKEN_PATH));
    oauth2Client.setCredentials(token);

    const youtube = google.youtube({
      version: 'v3',
      auth: oauth2Client
    });

    console.log('1. Fetching your Channel ID...');
    // Fetch the user's channel ID
    const channelListResponse = await youtube.channels.list({
      mine: true,
      part: 'id,brandingSettings'
    });

    if (channelListResponse.data.items.length === 0) {
      console.log('❌ No YouTube channel found for this Google Account.');
      return;
    }

    const channel = channelListResponse.data.items[0];
    console.log(`✅ Found Channel: ${channel.id}`);

    // Update settings
    console.log('2. Applying high-converting SEO Tags and targeting UK (GB)...');
    
    // We must pass the entire brandingSettings object back, updated.
    const currentBranding = channel.brandingSettings || {};
    const channelSettings = currentBranding.channel || {};

    // Inject our optimized settings
    channelSettings.title = 'Pound for Pound Finance';
    channelSettings.description = 'Welcome to Pound for Pound Finance — your ultimate blueprint for building wealth, mastering money, and achieving financial freedom.\n\nMost people are kept poor by habits they don\'t even realize they have. We break down the complex worlds of investing, personal finance, side hustles, and wealth psychology into simple, actionable steps that actually work.\n\n📈 Subscribe for weekly videos on money habits, market insights, and the exact strategies the top 1% use to grow their net worth.\n\n"It\'s not about how much money you make, but how much money you keep, how hard it works for you, and how many generations you keep it for."';
    channelSettings.keywords = '"finance" "wealth building" "UK investing" "personal finance" "money habits" "Pound for Pound Finance" "passive income" "stock market" "financial independence" "UK housing market"';
    channelSettings.country = 'GB';
    channelSettings.defaultLanguage = 'en-GB';
    
    // Update the object
    currentBranding.channel = channelSettings;

    // Send the update to YouTube
    const updateResponse = await youtube.channels.update({
      part: 'brandingSettings',
      requestBody: {
        id: channel.id,
        brandingSettings: currentBranding
      }
    });

    console.log('\n🎉 SUCCESS! Your channel has been fully optimized.');
    console.log('Updated Keywords:', updateResponse.data.brandingSettings.channel.keywords);
    console.log('Target Country:', updateResponse.data.brandingSettings.channel.country);

  } catch (error) {
    console.error('\n❌ Error optimizing channel:', error.message);
    if (error.response && error.response.data) {
      console.error('API Error Details:', JSON.stringify(error.response.data, null, 2));
    }
  }
}

optimizeChannel();
