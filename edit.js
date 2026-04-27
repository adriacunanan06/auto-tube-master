const ffmpeg = require('fluent-ffmpeg');
const ffmpegInstaller = require('ffmpeg-static');
const path = require('path');
const fs = require('fs');

ffmpeg.setFfmpegPath(ffmpegInstaller);

// Helper to escape text for FFmpeg drawtext
function escapeDrawtext(text) {
  if (!text) return '';
  // Remove single quotes and colons entirely for maximum FFmpeg stability in filtergraphs
  return text.replace(/'/g, "").replace(/:/g, "");
}

async function renderScene(sceneData, index, outputPath) {
  return new Promise((resolve, reject) => {
    // Probe audio length
    ffmpeg.ffprobe(sceneData.audioPath, (err, metadata) => {
      let duration = 5;
      if (!err && metadata && metadata.format && metadata.format.duration) {
        duration = metadata.format.duration;
      }
      
      const caption = escapeDrawtext(sceneData.caption || '');
      
      // 1. Scale/Crop to 1080x1920
      // 2. Draw text in the middle
      // Simplified drawtext filter to avoid "Invalid argument" errors on Windows
      const filtergraph = `[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[bg];[bg]drawtext=text='${caption}':fontcolor=white:fontsize=80:x=(w-text_w)/2:y=(h-text_h)/2:borderw=4:bordercolor=black[v]`;

      ffmpeg()
        .input(sceneData.videoPath)
        .inputOptions(['-stream_loop', '-1']) // Loop video in case it's shorter than audio
        .input(sceneData.audioPath)
        .complexFilter(filtergraph, 'v')
        .outputOptions([
          '-map 1:a:0',
          '-c:v libx264',
          '-preset fast',
          '-c:a aac',
          '-b:a 192k',
          `-t ${duration}`,
          '-pix_fmt yuv420p',
          '-shortest'
        ])
        .save(outputPath)
        .on('start', (cmd) => console.log(`FFmpeg Scene ${index} Command:`, cmd))
        .on('end', () => resolve(outputPath))
        .on('error', (err) => reject(err));
    });
  });
}

async function createFinalVideo(processedScenes, finalOutputPath) {
  console.log('\\n🎞️ Rendering 48 individual cinematic scenes (this will take time)...');
  
  if (processedScenes.length === 0) {
    throw new Error("No scenes provided");
  }

  const tempDir = path.dirname(processedScenes[0].videoPath);
  const renderedPaths = [];

  for (let i = 0; i < processedScenes.length; i++) {
    console.log(`Rendering Scene ${i + 1}/${processedScenes.length}...`);
    const sceneOut = path.join(tempDir, `rendered_scene_${i}.mp4`);
    await renderScene(processedScenes[i], i, sceneOut);
    renderedPaths.push(sceneOut);
  }

  console.log('\\n🎞️ Concatenating all scenes into final video...');
  const concatFilePath = path.join(tempDir, 'concat_final.txt');
  let concatLines = '';
  for (const p of renderedPaths) {
    // Windows paths in FFmpeg concat file must use forward slashes
    const normalizedPath = p.replace(/\\\\/g, '/');
    concatLines += `file '${normalizedPath}'\n`;
  }
  fs.writeFileSync(concatFilePath, concatLines);

  return new Promise((resolve, reject) => {
    ffmpeg()
      .input(concatFilePath)
      .inputOptions(['-f concat', '-safe 0'])
      .outputOptions([
        '-c:v copy',
        '-c:a copy'
      ])
      .save(finalOutputPath)
      .on('end', () => {
        console.log('✅ Final stitched cinematic video created at:', finalOutputPath);
        resolve(finalOutputPath);
      })
      .on('error', (err) => {
        console.error('❌ Error creating final video:', err.message);
        reject(err);
      });
  });
}

module.exports = { createFinalVideo };
