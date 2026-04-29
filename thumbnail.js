const axios = require('axios');
const fs = require('fs');
const path = require('path');
const ffmpeg = require('fluent-ffmpeg');
const ffmpegInstaller = require('ffmpeg-static');
require('dotenv').config();

ffmpeg.setFfmpegPath(ffmpegInstaller);

async function downloadImage(url, outputPath) {
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

async function fetchThumbnailPhoto(query, outputPath) {
  console.log(`📸 Fetching Thumbnail Background for query: "${query}"...`);
  const apiKey = process.env.PEXELS_API_KEY;

  try {
    const response = await axios.get(`https://api.pexels.com/v1/search`, {
      headers: { Authorization: apiKey },
      params: { query, per_page: 1, orientation: 'landscape' }
    });

    const photos = response.data.photos;
    if (!photos || photos.length === 0) {
      console.warn('⚠️ No photos found for thumbnail. Using fallback.');
      return null;
    }

    const bestPhoto = photos[0].src.large2x;
    await downloadImage(bestPhoto, outputPath);
    return outputPath;
  } catch (error) {
    console.error('❌ Error fetching thumbnail photo:', error.message);
    return null;
  }
}

async function createThumbnail(backgroundPath, text, outputPath) {
  console.log(`🎨 Creating thumbnail with text: "${text}"...`);
  
  return new Promise((resolve, reject) => {
    // Escape text for FFmpeg
    const cleanText = text.replace(/'/g, "").replace(/:/g, "").toUpperCase();
    
    ffmpeg(backgroundPath)
      .outputOptions([
        '-vf', `scale=1280:720,drawtext=text='${cleanText}':fontcolor=white:fontsize=100:x=(w-text_w)/2:y=(h-text_h)/2:borderw=10:bordercolor=black:box=1:boxcolor=black@0.5:boxborderw=20`
      ])
      .frames(1)
      .save(outputPath)
      .on('end', () => {
        console.log('✅ Thumbnail created at:', outputPath);
        resolve(outputPath);
      })
      .on('error', (err) => {
        console.error('❌ Error creating thumbnail:', err.message);
        reject(err);
      });
  });
}

module.exports = { fetchThumbnailPhoto, createThumbnail };
