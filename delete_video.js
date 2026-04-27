const { google } = require('googleapis');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

const TOKEN_PATH = path.join(__dirname, 'youtube-token.json');
const VIDEO_ID = '_vy9rqFU-wU'; // The video to delete

async function deleteVideo() {
  console.log(`🗑️ Attempting to delete video: ${VIDEO_ID}...`);
  
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

    await youtube.videos.delete({
      id: VIDEO_ID
    });

    console.log('✅ Video successfully deleted from YouTube.');
  } catch (error) {
    console.error('❌ Error deleting video:', error.message);
  }
}

deleteVideo();
