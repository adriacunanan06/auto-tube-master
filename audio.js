const axios = require('axios');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

async function generateAudio(text, outputPath) {
  console.log('🎙️ Generating voiceover with ElevenLabs...');
  
  const voiceId = process.env.ELEVENLABS_VOICE_ID || 'pNInz6obpgDQGcFmaJgB'; // Adam
  const apiKey = process.env.ELEVENLABS_API_KEY;

  if (!apiKey) {
    throw new Error('Missing ELEVENLABS_API_KEY in .env file');
  }

  const url = `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}`;

  try {
    const response = await axios({
      method: 'POST',
      url: url,
      headers: {
        'Accept': 'audio/mpeg',
        'xi-api-key': apiKey,
        'Content-Type': 'application/json'
      },
      data: {
        text: text,
        model_id: 'eleven_multilingual_v2',
        voice_settings: {
          stability: 0.5,
          similarity_boost: 0.75
        }
      },
      responseType: 'stream'
    });

    const writer = fs.createWriteStream(outputPath);
    response.data.pipe(writer);

    return new Promise((resolve, reject) => {
      writer.on('finish', resolve);
      writer.on('error', reject);
    });
  } catch (error) {
    console.error('❌ Error generating audio:', error.response ? error.response.data : error.message);
    throw error;
  }
}

module.exports = { generateAudio };
