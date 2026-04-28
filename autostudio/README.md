# Autonomous Faceless Content Studio

`autostudio.py` is an end-to-end automation tool that creates faceless finance content with minimal manual work:

1. Picks/validates a topic (with trend hints)
2. Generates title, hook, script, description, hashtags, thumbnail ideas, and affiliate offer ideas
3. Generates voiceover (ElevenLabs or free edge-tts fallback)
4. Builds a vertical or horizontal video with subtitles
5. Produces platform-ready post captions
6. Produces a monetization plan markdown file
7. Optionally uploads directly to YouTube
8. Can run in batch mode and be scheduled daily on Windows

## 1) Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2) Configure

```powershell
Copy-Item .env.example .env
```

Edit `.env`:

- Set `GEMINI_API_KEY` or `OPENAI_API_KEY` (recommended for best script quality)
- Optional:
  - `ELEVENLABS_API_KEY` for premium voice
  - `PEXELS_API_KEY` for stock image B-roll
  - `YOUTUBE_CLIENT_SECRETS_FILE` for auto-upload

If optional keys are missing, the tool still works with fallbacks.

## 3) Run once (autopilot)

```powershell
python autostudio.py run
```

## 4) Run batch autopilot

Creates multiple monetization-ready videos in one go:

```powershell
python autostudio.py run --batch 5 --sleep-seconds 4 --upload-youtube --privacy private
```

## 5) Run with a fixed topic

```powershell
python autostudio.py run --topic "How to Save Your First $1,000 Fast" --format short
```

## 6) Dry run (content-only, no video render)

```powershell
python autostudio.py run --dry-run
```

## 7) Schedule daily automation (Windows Task Scheduler)

```powershell
python autostudio.py install-task --time 09:00 --batch 2 --upload-youtube --privacy private
```

This creates a daily task called `FacelessAutoStudio`.

## Output structure

Each job creates a folder in `outputs/` containing:

- `content_package.json`
- `content_package.md`
- `platform_posts.json`
- `monetization_plan.md`
- `voiceover.mp3`
- `captions.srt` (unless disabled)
- `final_video.mp4`
- `youtube_upload.json` (if uploaded)
- `assets/` (downloaded or generated slide images)

Batch runs also produce `batch_summary_*.json`.

## Important for real monetization

- Keep content original and useful to avoid inauthentic/reused-content monetization issues.
- Add proper affiliate/sponsorship disclosures.
- Use long-term consistency: this tool automates production, but channel growth still needs repeated publishing and iteration.

