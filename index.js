const fs = require('fs');
const path = require('path');
const { generateScript } = require('./gemini');
const { generateAudio } = require('./audio');
const { fetchBroll } = require('./video');
const { createFinalVideo } = require('./edit');
const { uploadToYouTube, setThumbnail } = require('./upload');

// Create temp directory for storing assets
const tempDir = path.join(__dirname, 'temp');
if (!fs.existsSync(tempDir)) {
  fs.mkdirSync(tempDir);
}

async function runPipeline(topic) {
  try {
    console.log(`\n===========================================`);
    console.log(`🚀 STARTING AUTO-TUBE PIPELINE`);
    console.log(`📈 Topic: ${topic}`);
    console.log(`===========================================\n`);

    // 1. Generate Script
    const scriptData = await generateScript(topic);
    console.log('\n📜 Script Generated:');
    console.log(`Title: ${scriptData.title}`);
    
    // 3. Process Scene by Scene
    const scenes = scriptData.scenes;
    const processedScenes = [];

    console.log(`\n🎬 Processing ${scenes.length} cinematic scenes...`);
    
    // We will process a subset if 48 scenes takes too long, but let's do all of them for now
    for (let i = 0; i < scenes.length; i++) {
        const scene = scenes[i];
        console.log(`\n-- Scene ${i + 1}/${scenes.length} --`);
        
        // Audio
        const audioPath = path.join(tempDir, `scene_${i}.mp3`);
        await generateAudio(scene.voiceover, audioPath);
        
        // Video
        const videoPath = path.join(tempDir, `scene_broll_${i}.mp4`);
        const downloadedVideo = await fetchBroll(scene.visual_query, videoPath);
        
        if (downloadedVideo) {
            processedScenes.push({
                videoPath: downloadedVideo,
                audioPath: audioPath,
                caption: scene.caption
            });
        } else {
            console.warn(`⚠️ Skipping scene ${i + 1} due to missing B-roll`);
        }
    }

    if (processedScenes.length === 0) {
        throw new Error('Failed to download any scenes. Cannot proceed.');
    }

    // 4. Stitch Video and Audio
    const finalOutputPath = path.join(__dirname, 'final_output.mp4');
    await createFinalVideo(processedScenes, finalOutputPath);

    // 5. Upload to YouTube
    const videoId = await uploadToYouTube(finalOutputPath, scriptData.title, scriptData.description);

    // 6. Set Thumbnail if available
    const thumbnailPath = path.join(tempDir, 'thumbnail.png');
    if (videoId && fs.existsSync(thumbnailPath)) {
        await setThumbnail(videoId, thumbnailPath);
    }

    console.log(`\n🎉 PIPELINE COMPLETE! Your video is ready at: ${finalOutputPath}`);

  } catch (error) {
    console.error(`\n❌ PIPELINE FAILED:`, error.message);
  }
}

// Example usage
const targetTopic = process.argv[2] || "5 Money Habits Keeping You Poor";
runPipeline(targetTopic);
