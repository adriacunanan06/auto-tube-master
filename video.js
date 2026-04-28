const axios = require('axios');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

async function downloadVideo(url, outputPath) {
  const writer = fs.createWriteStream(outputPath);
  
  const response = await axios({
    url,
    method: 'GET',
    responseType: 'stream'
  });

  response.data.pipe(writer);

  return new Promise((resolve, reject) => {
    writer.on('finish', resolve);
    writer.on('error', reject);
  });
}

async function fetchBroll(query, outputPath) {
  console.log(`🎬 Fetching B-Roll for query: "${query}"...`);
  const apiKey = process.env.PEXELS_API_KEY;

  if (!apiKey) {
    throw new Error('Missing PEXELS_API_KEY in .env file');
  }

  try {
    const response = await axios.get(`https://api.pexels.com/videos/search`, {
      headers: {
        Authorization: apiKey
      },
      params: {
        query: query,
        per_page: 5,
        orientation: 'landscape' // YouTube Widescreen format
      }
    });

    const videos = response.data.videos;
    if (!videos || videos.length === 0) {
      console.warn(`⚠️ No videos found for query "${query}". Trying fallback...`);
      return null;
    }

    // Pick the first video and find the HD file
    const bestVideo = videos[0];
    const videoFiles = bestVideo.video_files;
    
    // Prioritize HD but keep file size reasonable
    let selectedFile = videoFiles.find(f => f.quality === 'hd' && f.height >= 1080);
    if (!selectedFile) {
      selectedFile = videoFiles[0]; // fallback to whatever is available
    }

    await downloadVideo(selectedFile.link, outputPath);
    console.log(`✅ Downloaded B-roll for "${query}"`);
    return outputPath;

  } catch (error) {
    console.error(`❌ Error fetching video for "${query}":`, error.response ? error.response.data : error.message);
    return null;
  }
}

module.exports = { fetchBroll };
