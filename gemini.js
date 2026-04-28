const { GoogleGenerativeAI } = require('@google/generative-ai');
require('dotenv').config();

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);

async function generateScript(topic) {
  console.log(`🧠 Generating script for topic: "${topic}" using Gemini...`);
  const model = genAI.getGenerativeModel({ model: 'gemini-2.5-flash' });

  const prompt = `
You are a cinematic YouTube video generator for the UK personal finance channel 'Pound for Pound Finance'.

Your job is to create a HIGH-RETENTION, CINEMATIC, SCENE-BY-SCENE script for a UK finance video.

Each scene MUST include:
* Voiceover (1 short sentence only)
* Visual (specific, cinematic, realistic b-roll)
* Motion (camera movement or animation)
* On-screen text (short, punchy captions)
* Emotion (tone of the scene)

SCENE RULES:
* 5–7 seconds per scene
* No long sentences
* No paragraphs
* One idea per scene
* Max clarity

STYLE:
* Style: Cinematic widescreen (16:9)
* Real-life UK visuals (London streets, Tesco, bills, banking apps, rent, etc.)

STRUCTURE:
HOOK (Scene 1–4)
* Pattern interrupt + curiosity
* Must feel urgent or shocking

BUILD PAIN (Scene 5–10)
* Cost of living
* Bills, rent, inflation
* Make viewer feel it

VALUE (Scene 11–30)
* 3–5 tips
* Each tip split into multiple scenes

STORY (Scene 31–36)
* Realistic UK example (person saving or earning money)

RE-ENGAGE (Scene 37–40)
* “Most people miss this…”

FINAL PUSH (Scene 41–45)
* Strong takeaway

CTA (Scene 46–48)
* Explicitly tell viewers to subscribe to 'Pound for Pound Finance'.
* IMPORTANT: Use "host" as the visual_query for Scene 1 (Hook) and Scene 48 (CTA) and occasionally throughout the video to show the AI Narrator.

VISUAL RULES:
* Use "host" as the visual_query for scenes where the AI Narrator should be on screen.
* No generic “stock footage”
* Be VERY specific
* Example: “close-up of UK electricity bill showing £300+”
* Example: “person checking bank app with low balance”

MOTION RULES:
* Always include movement (zoom, swipe, scroll, pan)

CAPTIONS:
* Big, bold, emotional
* 2–5 words max

TOPIC:
${topic}

GOAL:
* No looping
* Perfect sync
* Cinematic feel
* High retention

OUTPUT REQUIREMENTS (CRITICAL!):
You MUST output your ENTIRE response as a strictly valid JSON object matching the exact structure below. Do not include markdown formatting like \`\`\`json. Output ONLY the raw JSON string.

{
  "title": "One of your 5 clickable YouTube titles",
  "description": "Your optimized description",
  "scenes": [
    {
      "voiceover": "The exact short sentence to be spoken",
      "visual_query": "A 2-3 word search term to find a stock video on Pexels that matches this scene",
      "caption": "Short bold words for on-screen text",
      "motion": "zoom / pan / cut",
      "emotion": "urgent"
    }
  ]
}
`;

  try {
    const result = await model.generateContent(prompt);
    const responseText = result.response.text();
    
    // Clean up markdown if the AI adds it
    let cleanJson = responseText;
    if (cleanJson.startsWith('\`\`\`json')) {
      cleanJson = cleanJson.substring(7, cleanJson.length - 3);
    }
    if (cleanJson.startsWith('\`\`\`')) {
      cleanJson = cleanJson.substring(3, cleanJson.length - 3);
    }

    return JSON.parse(cleanJson);
  } catch (error) {
    console.error('❌ Error generating script:', error);
    throw error;
  }
}

module.exports = { generateScript };
