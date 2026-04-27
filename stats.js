const { google } = require('googleapis');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

const TOKEN_PATH = path.join(__dirname, 'youtube-token.json');

async function getYouTubeStats() {
  console.log('📊 Fetching Real YouTube Analytics...');
  
  if (!fs.existsSync(TOKEN_PATH)) {
      console.warn('⚠️ No youtube-token.json found!');
      return null;
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

    // 1. Get Channel Stats
    const channelRes = await youtube.channels.list({
      part: 'statistics,snippet',
      mine: true
    });

    if (!channelRes.data.items || channelRes.data.items.length === 0) {
      throw new Error('Channel not found');
    }

    const stats = channelRes.data.items[0].statistics;
    const snippet = channelRes.data.items[0].snippet;

    // 2. Get Recent Videos
    const activitiesRes = await youtube.activities.list({
      part: 'snippet,contentDetails',
      mine: true,
      maxResults: 5
    });

    const recentVideos = activitiesRes.data.items
      .filter(item => item.snippet.type === 'upload')
      .map(item => ({
        title: item.snippet.title,
        publishedAt: item.snippet.publishedAt,
        thumbnail: item.snippet.thumbnails.high.url,
        videoId: item.contentDetails.upload.videoId
      }));

    const data = {
      channelName: snippet.title,
      totalViews: stats.viewCount,
      subscribers: stats.subscriberCount,
      videoCount: stats.videoCount,
      recentVideos: recentVideos,
      lastUpdated: new Date().toISOString()
    };

    console.log('✅ Real stats fetched successfully!');
    return data;

  } catch (error) {
    console.error('❌ Error fetching YouTube stats:', error.message);
    return null;
  }
}

module.exports = { getYouTubeStats };
