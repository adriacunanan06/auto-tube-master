const { google } = require('googleapis');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

const TOKEN_PATH = path.join(__dirname, 'youtube-token.json');

async function uploadToYouTube(videoPath, title, description) {
  console.log('🚀 Initiating YouTube Upload...');
  
  if (!process.env.YOUTUBE_CLIENT_ID || !process.env.YOUTUBE_CLIENT_SECRET) {
      console.warn('⚠️ YouTube API credentials missing. Skipping upload step.');
      return;
  }

  if (!fs.existsSync(TOKEN_PATH)) {
      console.warn('⚠️ No youtube-token.json found! You must run `node auth.js` first to authorize the app.');
      return;
  }

  try {
    const oauth2Client = new google.auth.OAuth2(
      process.env.YOUTUBE_CLIENT_ID,
      process.env.YOUTUBE_CLIENT_SECRET,
      process.env.YOUTUBE_REDIRECT_URI || 'http://localhost:3000/oauth2callback'
    );

    // Load the cached token
    const token = JSON.parse(fs.readFileSync(TOKEN_PATH));
    oauth2Client.setCredentials(token);

    const youtube = google.youtube({
      version: 'v3',
      auth: oauth2Client
    });

    console.log(`Uploading: "${title}"...`);

    const res = await youtube.videos.insert({
      part: 'snippet,status',
      requestBody: {
        snippet: {
          title: title.substring(0, 100), // Max length 100
          description: description,
          tags: ['finance', 'wealth', 'shorts', 'motivation'],
          categoryId: '27' // Education
        },
        status: {
          privacyStatus: 'public', // Fully autonomous mode!
          selfDeclaredMadeForKids: false
        }
      },
      media: {
        body: fs.createReadStream(videoPath)
      }
    });

    console.log(`✅ Upload Successful! Video ID: ${res.data.id}`);
    console.log(`Watch it here: https://youtu.be/${res.data.id}`);
    return res.data.id;

  } catch (error) {
    console.error('❌ Error uploading to YouTube:', error.message);
    if (error.response && error.response.data) {
      console.error(error.response.data);
    }
  }
}

async function setThumbnail(videoId, imagePath) {
  console.log(`🖼️ Setting custom thumbnail for video: ${videoId}...`);
  
  if (!fs.existsSync(TOKEN_PATH)) return;

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

    await youtube.thumbnails.set({
      videoId: videoId,
      media: {
        body: fs.createReadStream(imagePath)
      }
    });

    console.log('✅ Thumbnail successfully updated!');
  } catch (error) {
    console.error('❌ Error setting thumbnail:', error.message);
  }
}

module.exports = { uploadToYouTube, setThumbnail };
