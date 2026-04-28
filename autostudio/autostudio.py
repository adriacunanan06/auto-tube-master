from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import subprocess
import sys
import textwrap
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

try:
    import edge_tts
except ImportError:
    edge_tts = None

try:
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except ImportError:
    GoogleRequest = None
    Credentials = None
    InstalledAppFlow = None
    build = None
    MediaFileUpload = None


ROOT = Path(__file__).resolve().parent
OUTPUTS_DIR = ROOT / "outputs"
YOUTUBE_UPLOAD_SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]

DEFAULT_EVERGREEN_TOPICS = [
    "7 money habits quietly keeping people broke",
    "how to build an emergency fund from zero",
    "the beginner investing mistakes that cost years of growth",
    "how compound interest actually builds wealth over time",
    "a simple paycheck budget that works on low income",
    "how debt snowball vs avalanche changes your payoff timeline",
    "why most people stay paycheck to paycheck and how to break it",
    "simple side-hustle budgeting system for beginners",
]

FINANCE_KEYWORDS = {
    "finance",
    "money",
    "stocks",
    "investing",
    "economy",
    "budget",
    "inflation",
    "interest rates",
    "credit",
    "debt",
    "recession",
    "mortgage",
}


@dataclass
class ContentPackage:
    topic: str
    angle: str
    title: str
    alternative_titles: list[str]
    hook: str
    script: str
    description: str
    hashtags: list[str]
    tags: list[str]
    thumbnail_ideas: list[str]
    broll_keywords: list[str]
    call_to_action: str
    disclaimer: str
    affiliate_offer_ideas: list[str]


def log(message: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {message}")


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "topic"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def safe_json_load(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response.")
    return json.loads(match.group(0))


def run_cmd(command: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=check,
    )


def ffprobe_duration_seconds(audio_file: Path) -> float:
    result = run_cmd(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_file),
        ]
    )
    return max(1.0, float(result.stdout.strip()))


def fetch_google_trends(geo: str = "US") -> list[str]:
    url = f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={geo}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except requests.RequestException:
        return []

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return []

    titles: list[str] = []
    for item in root.findall(".//item"):
        title = item.findtext("title")
        if title:
            titles.append(title.strip())
    return titles[:30]


class LLMClient:
    def __init__(self) -> None:
        self.provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()

    @property
    def configured(self) -> bool:
        if self.provider == "openai":
            return bool(self.openai_api_key)
        return bool(self.gemini_api_key or self.openai_api_key)

    def _call_gemini(self, prompt: str, temperature: float = 0.7) -> str:
        if not self.gemini_api_key:
            raise ValueError("Missing GEMINI_API_KEY")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }
        response = requests.post(
            url,
            params={"key": self.gemini_api_key},
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        body = response.json()
        candidates = body.get("candidates", [])
        if not candidates:
            raise ValueError(f"Gemini returned no candidates: {body}")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts).strip()
        if not text:
            raise ValueError(f"Gemini returned empty text: {body}")
        return text

    def _call_openai(self, prompt: str, temperature: float = 0.7) -> str:
        if not self.openai_api_key:
            raise ValueError("Missing OPENAI_API_KEY")
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": self.openai_model,
            "temperature": temperature,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise content strategist. Follow output format exactly.",
                },
                {"role": "user", "content": prompt},
            ],
        }
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {self.openai_api_key}"},
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        body = response.json()
        choices = body.get("choices", [])
        if not choices:
            raise ValueError(f"OpenAI returned no choices: {body}")
        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise ValueError(f"OpenAI returned empty content: {body}")
        return content.strip()

    def generate_text(self, prompt: str, temperature: float = 0.7) -> str:
        if self.provider == "openai":
            return self._call_openai(prompt, temperature=temperature)
        if self.provider == "gemini":
            if self.gemini_api_key:
                return self._call_gemini(prompt, temperature=temperature)
            if self.openai_api_key:
                return self._call_openai(prompt, temperature=temperature)
            raise ValueError("No API key configured for Gemini/OpenAI.")
        if self.gemini_api_key:
            return self._call_gemini(prompt, temperature=temperature)
        if self.openai_api_key:
            return self._call_openai(prompt, temperature=temperature)
        raise ValueError("No LLM provider configured.")

    def generate_json(self, prompt: str, temperature: float = 0.7) -> dict[str, Any]:
        text = self.generate_text(prompt=prompt, temperature=temperature)
        return safe_json_load(text)


def pick_topic(
    llm: LLMClient,
    user_topic: str | None,
    niche: str,
    target_audience: str,
    geo: str,
) -> tuple[str, str]:
    if user_topic:
        return user_topic.strip(), f"{user_topic.strip()} for {target_audience}"

    trends = fetch_google_trends(geo=geo)
    finance_trends = [
        t for t in trends if any(keyword in t.lower() for keyword in FINANCE_KEYWORDS)
    ]
    candidate_topics = (finance_trends + DEFAULT_EVERGREEN_TOPICS)[:20]

    if llm.configured:
        prompt = f"""
Pick one YouTube topic in the niche "{niche}" for audience "{target_audience}".
Goal: high click-through + high retention.
Input candidates: {candidate_topics}

Return strict JSON with:
{{
  "topic": "short topic",
  "angle": "one-sentence unique angle"
}}
"""
        try:
            data = llm.generate_json(prompt, temperature=0.6)
            topic = str(data.get("topic", "")).strip()
            angle = str(data.get("angle", "")).strip()
            if topic and angle:
                return topic, angle
        except Exception as exc:
            log(f"Topic selection with LLM failed, falling back. Reason: {exc}")

    topic = random.choice(DEFAULT_EVERGREEN_TOPICS)
    angle = f"{topic} explained in a simple, beginner-friendly way for {target_audience}."
    return topic, angle


def template_package(topic: str, angle: str, audience: str) -> ContentPackage:
    script = (
        f"Most people never build wealth because they repeat a few small money mistakes for years. "
        f"Today we are breaking down {topic}. "
        "First, define a clear monthly number you want to save, even if it starts small. "
        "Second, automate that transfer right after payday so discipline is built into your system. "
        "Third, remove high-interest debt aggressively because that interest is silently stealing your future income. "
        "Fourth, use a simple investing rule you can sustain for years, not days. "
        "Fifth, track progress weekly so your decisions improve with real data. "
        "Consistency beats intensity. "
        "Small actions repeated every month can compound into life-changing results over time."
    )
    return ContentPackage(
        topic=topic,
        angle=angle,
        title=f"{topic.title()}: A Simple System That Actually Works",
        alternative_titles=[
            f"{topic.title()} (Beginner Playbook)",
            f"Stop Losing Money: {topic.title()}",
            f"{topic.title()} Without Overthinking",
            f"How To Fix {topic.title()} Fast",
            f"{topic.title()} in Plain English",
        ],
        hook=f"If you only fix one money system this month, make it this: {topic}.",
        script=script,
        description=(
            f"In this video we break down {topic} in a clear step-by-step format for {audience}. "
            "Educational content only, not financial advice."
        ),
        hashtags=["#finance", "#money", "#wealth", "#budgeting", "#investing"],
        tags=["finance", "money tips", "budget", "investing basics", "wealth building"],
        thumbnail_ideas=[
            "Split screen: left chaotic bills, right clean budget tracker",
            "Large text: STOP LOSING MONEY with red arrow to hidden fee",
            "Before/after bank balance visual with strong contrast",
        ],
        broll_keywords=["budget planning", "credit card bill", "stock chart", "saving money"],
        call_to_action="Subscribe for practical money systems every week.",
        disclaimer="For education only. Not financial advice.",
        affiliate_offer_ideas=[
            "budgeting app free trial",
            "high-yield savings account comparison tool",
            "beginner investing course or template",
        ],
    )


def normalize_string_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        out = [str(x).strip() for x in value if str(x).strip()]
        if out:
            return out
    return fallback


def generate_content_package(
    llm: LLMClient,
    topic: str,
    angle: str,
    niche: str,
    audience: str,
    duration_seconds: int,
    content_format: str,
) -> ContentPackage:
    if not llm.configured:
        return template_package(topic, angle, audience)

    prompt = f"""
You are writing an ORIGINAL faceless YouTube content package.
Niche: {niche}
Topic: {topic}
Angle: {angle}
Audience: {audience}
Target duration (seconds): {duration_seconds}
Format: {content_format}

Constraints:
- High-retention, clear, concrete.
- Original writing only; no copy-paste vibe.
- Educational tone, not guaranteed-return claims.
- Include a short educational disclaimer.
- Keep script highly scannable and voiceover-ready.

Return strict JSON only with this shape:
{{
  "title": "main title",
  "alternative_titles": ["title1", "title2", "title3", "title4", "title5"],
  "hook": "single compelling opening line",
  "script": "full narration script",
  "description": "youtube description with CTA",
  "hashtags": ["#a", "#b", "#c", "#d", "#e"],
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6"],
  "thumbnail_ideas": ["idea1", "idea2", "idea3"],
  "broll_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5", "keyword6"],
  "call_to_action": "one sentence CTA",
  "disclaimer": "one short sentence",
  "affiliate_offer_ideas": ["offer1", "offer2", "offer3"]
}}
"""
    try:
        data = llm.generate_json(prompt, temperature=0.8)
    except Exception as exc:
        log(f"LLM package generation failed, using template package. Reason: {exc}")
        return template_package(topic, angle, audience)

    fallback = template_package(topic, angle, audience)
    return ContentPackage(
        topic=topic,
        angle=angle,
        title=str(data.get("title", fallback.title)).strip() or fallback.title,
        alternative_titles=normalize_string_list(
            data.get("alternative_titles"), fallback.alternative_titles
        ),
        hook=str(data.get("hook", fallback.hook)).strip() or fallback.hook,
        script=str(data.get("script", fallback.script)).strip() or fallback.script,
        description=str(data.get("description", fallback.description)).strip()
        or fallback.description,
        hashtags=normalize_string_list(data.get("hashtags"), fallback.hashtags),
        tags=normalize_string_list(data.get("tags"), fallback.tags),
        thumbnail_ideas=normalize_string_list(
            data.get("thumbnail_ideas"), fallback.thumbnail_ideas
        ),
        broll_keywords=normalize_string_list(
            data.get("broll_keywords"), fallback.broll_keywords
        ),
        call_to_action=str(data.get("call_to_action", fallback.call_to_action)).strip()
        or fallback.call_to_action,
        disclaimer=str(data.get("disclaimer", fallback.disclaimer)).strip()
        or fallback.disclaimer,
        affiliate_offer_ideas=normalize_string_list(
            data.get("affiliate_offer_ideas"), fallback.affiliate_offer_ideas
        ),
    )


def save_package_files(pkg: ContentPackage, out_dir: Path) -> None:
    ensure_dir(out_dir)
    json_file = out_dir / "content_package.json"
    md_file = out_dir / "content_package.md"

    json_file.write_text(json.dumps(asdict(pkg), indent=2, ensure_ascii=False), encoding="utf-8")

    md = []
    md.append(f"# {pkg.title}")
    md.append("")
    md.append(f"**Topic:** {pkg.topic}")
    md.append(f"**Angle:** {pkg.angle}")
    md.append("")
    md.append("## Hook")
    md.append(pkg.hook)
    md.append("")
    md.append("## Script")
    md.append(pkg.script)
    md.append("")
    md.append("## Description")
    md.append(pkg.description)
    md.append("")
    md.append("## Hashtags")
    md.append(" ".join(pkg.hashtags))
    md.append("")
    md.append("## Tags")
    md.append(", ".join(pkg.tags))
    md.append("")
    md.append("## Thumbnail Ideas")
    for idea in pkg.thumbnail_ideas:
        md.append(f"- {idea}")
    md.append("")
    md.append("## B-roll Keywords")
    for keyword in pkg.broll_keywords:
        md.append(f"- {keyword}")
    md.append("")
    md.append("## CTA")
    md.append(pkg.call_to_action)
    md.append("")
    md.append("## Disclaimer")
    md.append(pkg.disclaimer)
    md.append("")
    md.append("## Affiliate Offer Ideas")
    for offer in pkg.affiliate_offer_ideas:
        md.append(f"- {offer}")
    md.append("")

    md_file.write_text("\n".join(md), encoding="utf-8")


def default_platform_pack(pkg: ContentPackage) -> dict[str, str]:
    hashtags = " ".join(pkg.hashtags[:5])
    return {
        "youtube_title": pkg.title,
        "youtube_description_short": f"{pkg.description}\n\n{pkg.call_to_action}\n{pkg.disclaimer}",
        "youtube_pinned_comment": (
            f"What is your biggest challenge with {pkg.topic}? "
            "I read every comment and use them for the next videos."
        ),
        "shorts_caption": f"{pkg.hook} {hashtags}",
        "facebook_caption": f"{pkg.hook}\n\n{pkg.call_to_action}\n\n{hashtags}",
        "tiktok_caption": f"{pkg.hook} {hashtags}",
        "x_post": f"{pkg.title}: {pkg.hook} {hashtags}",
    }


def save_platform_pack(pkg: ContentPackage, llm: LLMClient, out_dir: Path) -> None:
    if not llm.configured:
        pack = default_platform_pack(pkg)
        (out_dir / "platform_posts.json").write_text(
            json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return

    prompt = f"""
Create platform-ready post copy for this finance video.
Title: {pkg.title}
Hook: {pkg.hook}
Description: {pkg.description}
Hashtags: {pkg.hashtags}

Return strict JSON:
{{
  "youtube_title": "...",
  "youtube_description_short": "...",
  "youtube_pinned_comment": "...",
  "shorts_caption": "...",
  "facebook_caption": "...",
  "tiktok_caption": "...",
  "x_post": "..."
}}
"""
    try:
        pack = llm.generate_json(prompt, temperature=0.7)
    except Exception as exc:
        log(f"Platform pack generation failed, using defaults. Reason: {exc}")
        pack = default_platform_pack(pkg)
    (out_dir / "platform_posts.json").write_text(
        json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def save_monetization_plan(pkg: ContentPackage, llm: LLMClient, out_dir: Path) -> None:
    default_plan = textwrap.dedent(
        f"""
        # Monetization Plan

        ## Primary Angle
        - Topic: {pkg.topic}
        - Core CTA: {pkg.call_to_action}

        ## Affiliate Ideas
        """
    ).strip("\n")
    lines = [default_plan]
    for offer in pkg.affiliate_offer_ideas:
        lines.append(f"- {offer}")
    lines.extend(
        [
            "",
            "## Revenue Stack",
            "- YouTube ads after YPP eligibility.",
            "- Affiliate links in description and pinned comment.",
            "- Optional digital product (budget template, debt tracker, habit tracker).",
            "",
            "## Compliance",
            "- Add clear paid/affiliate disclosure in description and comments.",
            f"- Keep disclaimer: {pkg.disclaimer}",
        ]
    )
    plan_md = "\n".join(lines)

    if llm.configured:
        prompt = f"""
Build a practical monetization plan for this content package.
Topic: {pkg.topic}
Audience: finance beginners
Affiliate ideas: {pkg.affiliate_offer_ideas}
CTA: {pkg.call_to_action}

Return markdown with:
1) Fastest path to first $100
2) 30-day posting cadence
3) Affiliate conversion tactics
4) Offer ladder (free lead magnet -> low ticket -> higher ticket)
5) Compliance checklist for disclosures
"""
        try:
            plan_md = llm.generate_text(prompt, temperature=0.7)
        except Exception as exc:
            log(f"Monetization plan generation failed, using default. Reason: {exc}")

    (out_dir / "monetization_plan.md").write_text(plan_md.strip() + "\n", encoding="utf-8")


def generate_voiceover(pkg: ContentPackage, output_file: Path) -> None:
    eleven_api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    eleven_voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip() or "EXAVITQu4vr4xnSDxMaL"
    eleven_model = os.getenv("ELEVENLABS_MODEL", "").strip() or "eleven_multilingual_v2"

    if eleven_api_key:
        log("Generating voiceover with ElevenLabs API...")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{eleven_voice_id}"
        payload = {
            "model_id": eleven_model,
            "text": pkg.script,
            "voice_settings": {"stability": 0.35, "similarity_boost": 0.7},
        }
        response = requests.post(
            url,
            headers={
                "xi-api-key": eleven_api_key,
                "accept": "audio/mpeg",
                "content-type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        output_file.write_bytes(response.content)
        return

    if edge_tts is None:
        raise RuntimeError(
            "No ELEVENLABS_API_KEY set and edge-tts is not installed. Install dependencies first."
        )

    voice = os.getenv("EDGE_TTS_VOICE", "en-US-AriaNeural").strip()
    log(f"Generating voiceover with edge-tts voice {voice}...")
    communicate = edge_tts.Communicate(pkg.script, voice=voice)
    asyncio.run(communicate.save(str(output_file)))


def download_file(url: str, target: Path) -> bool:
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return False
    target.write_bytes(response.content)
    return True


def fetch_pexels_images(
    keywords: list[str], count: int, target_dir: Path, orientation: str
) -> list[Path]:
    api_key = os.getenv("PEXELS_API_KEY", "").strip()
    if not api_key:
        return []

    headers = {"Authorization": api_key}
    out: list[Path] = []
    seen_urls: set[str] = set()
    orientation_value = "portrait" if orientation == "short" else "landscape"
    queries = keywords + ["money", "finance office", "calculator", "budget"]

    for query in queries:
        if len(out) >= count:
            break
        try:
            response = requests.get(
                "https://api.pexels.com/v1/search",
                headers=headers,
                params={
                    "query": query,
                    "per_page": 8,
                    "orientation": orientation_value,
                    "size": "large",
                },
                timeout=30,
            )
            response.raise_for_status()
            photos = response.json().get("photos", [])
        except requests.RequestException:
            continue

        random.shuffle(photos)
        for photo in photos:
            if len(out) >= count:
                break
            src = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("large")
            if not src or src in seen_urls:
                continue
            seen_urls.add(src)
            target = target_dir / f"broll_{len(out) + 1:02d}.jpg"
            if download_file(src, target):
                out.append(target)
    return out


def split_sentences(text: str) -> list[str]:
    pieces = re.split(r"(?<=[.!?])\s+", text.strip())
    pieces = [p.strip() for p in pieces if p.strip()]
    if not pieces:
        return [text.strip()]
    return pieces


def slide_points_from_script(script: str, target_count: int) -> list[str]:
    sentences = split_sentences(script)
    cleaned = []
    for sentence in sentences:
        short = sentence.strip()
        short = re.sub(r"\s+", " ", short)
        if len(short) > 120:
            short = short[:117].rstrip() + "..."
        cleaned.append(short)
    if not cleaned:
        cleaned = ["Build wealth with simple repeatable habits."]

    points: list[str] = []
    step = max(1, len(cleaned) // target_count)
    for i in range(0, len(cleaned), step):
        points.append(cleaned[i])
        if len(points) >= target_count:
            break
    while len(points) < target_count:
        points.append(random.choice(cleaned))
    return points[:target_count]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    common_fonts = [
        "arial.ttf",
        "Arial.ttf",
        "segoeui.ttf",
        "SegoeUI.ttf",
        "calibri.ttf",
    ]
    for font_name in common_fonts:
        try:
            return ImageFont.truetype(font_name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def create_gradient_background(width: int, height: int, color_a: tuple[int, int, int], color_b: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (width, height), color_a)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        r = int(color_a[0] * (1 - ratio) + color_b[0] * ratio)
        g = int(color_a[1] * (1 - ratio) + color_b[1] * ratio)
        b = int(color_a[2] * (1 - ratio) + color_b[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    return image


def build_placeholder_slides(
    points: list[str],
    target_dir: Path,
    short_format: bool,
) -> list[Path]:
    ensure_dir(target_dir)
    width, height = (1080, 1920) if short_format else (1920, 1080)
    palettes = [
        ((12, 21, 39), (30, 58, 138)),
        ((17, 24, 39), (71, 85, 105)),
        ((41, 37, 36), (120, 53, 15)),
        ((15, 23, 42), (6, 182, 212)),
    ]
    title_font = load_font(72 if short_format else 64)
    body_font = load_font(52 if short_format else 42)
    small_font = load_font(34 if short_format else 28)
    out: list[Path] = []

    for idx, point in enumerate(points, start=1):
        color_a, color_b = palettes[(idx - 1) % len(palettes)]
        img = create_gradient_background(width, height, color_a, color_b)
        draw = ImageDraw.Draw(img)

        title = f"Money Move {idx}"
        title_box = draw.textbbox((0, 0), title, font=title_font)
        title_w = title_box[2] - title_box[0]
        draw.text(((width - title_w) / 2, height * 0.14), title, font=title_font, fill=(255, 255, 255))

        wrapped = textwrap.fill(point, width=26 if short_format else 38)
        text_box = draw.multiline_textbbox((0, 0), wrapped, font=body_font, spacing=12, align="center")
        text_w = text_box[2] - text_box[0]
        text_h = text_box[3] - text_box[1]
        draw.multiline_text(
            ((width - text_w) / 2, (height - text_h) / 2),
            wrapped,
            font=body_font,
            fill=(255, 255, 255),
            spacing=12,
            align="center",
        )

        footer = "Educational content only"
        footer_box = draw.textbbox((0, 0), footer, font=small_font)
        footer_w = footer_box[2] - footer_box[0]
        draw.text(((width - footer_w) / 2, height * 0.88), footer, font=small_font, fill=(230, 230, 230))

        slide_file = target_dir / f"slide_{idx:02d}.jpg"
        img.save(slide_file, quality=92)
        out.append(slide_file)
    return out


def format_srt_time(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours = milliseconds // 3_600_000
    minutes = (milliseconds % 3_600_000) // 60_000
    secs = (milliseconds % 60_000) // 1000
    ms = milliseconds % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def build_srt(script: str, duration_seconds: float, out_file: Path) -> None:
    sentences = split_sentences(script)
    if len(sentences) < 6:
        words = script.split()
        chunk_size = 10
        sentences = [
            " ".join(words[i : i + chunk_size]) for i in range(0, len(words), chunk_size)
        ]

    word_counts = [max(1, len(sentence.split())) for sentence in sentences]
    total_words = sum(word_counts)
    cursor = 0.0
    lines: list[str] = []

    for idx, sentence in enumerate(sentences, start=1):
        portion = word_counts[idx - 1] / total_words
        seg = max(1.0, duration_seconds * portion)
        start = cursor
        end = min(duration_seconds, cursor + seg)
        cursor = end
        text = textwrap.fill(sentence.strip(), width=42)
        lines.extend(
            [
                str(idx),
                f"{format_srt_time(start)} --> {format_srt_time(end)}",
                text,
                "",
            ]
        )
    out_file.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def build_concat_manifest(images: list[Path], duration_per_image: float, out_file: Path) -> None:
    if not images:
        raise ValueError("No images provided for slideshow manifest.")
    lines: list[str] = []
    for image in images:
        path = image.resolve().as_posix()
        lines.append(f"file '{path}'")
        lines.append(f"duration {duration_per_image:.3f}")
    lines.append(f"file '{images[-1].resolve().as_posix()}'")
    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def subtitle_path_for_ffmpeg(path: Path) -> str:
    # FFmpeg subtitles filter expects escaped drive colon on Windows.
    return path.resolve().as_posix().replace(":", "\\:")


def render_video(
    manifest: Path,
    audio_file: Path,
    srt_file: Path | None,
    output_file: Path,
    short_format: bool,
) -> None:
    width, height = (1080, 1920) if short_format else (1920, 1080)
    scale_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},format=yuv420p"
    )
    subtitle_style = (
        "FontName=Arial,FontSize=54,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=0,Alignment=2,MarginV=72"
    )

    if srt_file and srt_file.exists():
        subtitle_filter = (
            f"subtitles='{subtitle_path_for_ffmpeg(srt_file)}':"
            f"force_style='{subtitle_style}'"
        )
        vf = f"{scale_filter},{subtitle_filter}"
    else:
        vf = scale_filter

    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(manifest),
        "-i",
        str(audio_file),
        "-vf",
        vf,
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(output_file),
    ]

    try:
        run_cmd(command)
    except subprocess.CalledProcessError as exc:
        if srt_file and srt_file.exists():
            log("Subtitle burn failed; retrying render without subtitles...")
            fallback_command = command.copy()
            idx = fallback_command.index("-vf")
            fallback_command[idx + 1] = scale_filter
            run_cmd(fallback_command)
            return
        stderr = exc.stderr.strip() if exc.stderr else "No stderr output"
        raise RuntimeError(f"ffmpeg render failed: {stderr}") from exc


def upload_to_youtube(
    video_file: Path,
    pkg: ContentPackage,
    privacy_status: str,
    output_dir: Path,
) -> str:
    if not (GoogleRequest and Credentials and InstalledAppFlow and build and MediaFileUpload):
        raise RuntimeError(
            "YouTube dependencies are missing. Install requirements first."
        )

    client_secret_file = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "").strip()
    token_file = os.getenv("YOUTUBE_TOKEN_FILE", "").strip() or str(ROOT / "youtube_token.json")
    if not client_secret_file:
        raise RuntimeError("Set YOUTUBE_CLIENT_SECRETS_FILE in .env before uploading.")

    creds = None
    token_path = Path(token_file)
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), YOUTUBE_UPLOAD_SCOPE)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, YOUTUBE_UPLOAD_SCOPE)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    youtube = build("youtube", "v3", credentials=creds)

    description = f"{pkg.description}\n\n{pkg.call_to_action}\n\n{pkg.disclaimer}\n\n{' '.join(pkg.hashtags)}"
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": pkg.title[:100],
                "description": description[:5000],
                "tags": pkg.tags[:15],
                "categoryId": "27",  # Education
            },
            "status": {"privacyStatus": privacy_status},
        },
        media_body=MediaFileUpload(str(video_file), chunksize=-1, resumable=True),
    )

    response = None
    while response is None:
        _, response = request.next_chunk()

    video_id = response["id"]
    (output_dir / "youtube_upload.json").write_text(
        json.dumps(
            {
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "privacy_status": privacy_status,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return video_id


def youtube_upload_preflight() -> tuple[bool, str]:
    if not (GoogleRequest and Credentials and InstalledAppFlow and build and MediaFileUpload):
        return (
            False,
            "YouTube libraries are not available. Install requirements first.",
        )
    client_secret_file = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "").strip()
    if not client_secret_file:
        return (
            False,
            "YOUTUBE_CLIENT_SECRETS_FILE is not set in .env.",
        )
    if not Path(client_secret_file).exists():
        return (
            False,
            f'YOUTUBE_CLIENT_SECRETS_FILE path not found: "{client_secret_file}"',
        )
    return True, "ok"


def run_single_job(
    args: argparse.Namespace,
    llm: LLMClient,
    root_output_dir: Path,
    used_topics: set[str],
    topic_override: str | None,
    job_index: int,
    total_jobs: int,
) -> Path:
    topic_input = topic_override
    topic, angle = pick_topic(
        llm=llm,
        user_topic=topic_input,
        niche=args.niche,
        target_audience=args.audience,
        geo=args.geo,
    )

    if not topic_input and topic in used_topics:
        available = [t for t in DEFAULT_EVERGREEN_TOPICS if t not in used_topics]
        if available:
            topic = random.choice(available)
            angle = f"{topic} explained in a clear and practical format."
    used_topics.add(topic)

    job_name = topic or f"{args.niche}-autopilot"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"job{job_index:02d}" if total_jobs > 1 else "job01"
    out_dir = root_output_dir / f"{timestamp}_{suffix}_{slugify(job_name)}"
    ensure_dir(out_dir)
    assets_dir = out_dir / "assets"
    ensure_dir(assets_dir)
    log(f"[{job_index}/{total_jobs}] Selected topic: {topic}")

    pkg = generate_content_package(
        llm=llm,
        topic=topic,
        angle=angle,
        niche=args.niche,
        audience=args.audience,
        duration_seconds=args.duration,
        content_format=args.format,
    )
    save_package_files(pkg, out_dir)
    save_platform_pack(pkg, llm, out_dir)
    save_monetization_plan(pkg, llm, out_dir)
    log(f"[{job_index}/{total_jobs}] Content + monetization assets generated.")

    if args.dry_run:
        log(f"[{job_index}/{total_jobs}] Dry run complete: {out_dir}")
        return out_dir

    voice_file = out_dir / "voiceover.mp3"
    generate_voiceover(pkg, voice_file)
    log(f"[{job_index}/{total_jobs}] Voiceover generated.")

    audio_duration = ffprobe_duration_seconds(voice_file)
    log(f"[{job_index}/{total_jobs}] Audio duration: {audio_duration:.1f}s")

    srt_file: Path | None = None
    if not args.no_captions:
        srt_file = out_dir / "captions.srt"
        build_srt(pkg.script, audio_duration, srt_file)
        log(f"[{job_index}/{total_jobs}] Captions generated.")

    target_image_count = max(6, args.images)
    images = fetch_pexels_images(
        keywords=pkg.broll_keywords,
        count=target_image_count,
        target_dir=assets_dir,
        orientation=args.format,
    )
    if images:
        log(f"[{job_index}/{total_jobs}] Downloaded {len(images)} images from Pexels.")
    else:
        points = slide_points_from_script(pkg.script, target_image_count)
        images = build_placeholder_slides(points, assets_dir, short_format=args.format == "short")
        log(f"[{job_index}/{total_jobs}] Generated {len(images)} local slides.")

    manifest_file = out_dir / "slideshow.txt"
    duration_per_image = max(2.0, audio_duration / len(images))
    build_concat_manifest(images, duration_per_image, manifest_file)

    video_file = out_dir / "final_video.mp4"
    render_video(
        manifest=manifest_file,
        audio_file=voice_file,
        srt_file=srt_file,
        output_file=video_file,
        short_format=args.format == "short",
    )
    log(f"[{job_index}/{total_jobs}] Video rendered: {video_file.name}")

    if args.upload_youtube:
        log(f"[{job_index}/{total_jobs}] Uploading to YouTube...")
        try:
            video_id = upload_to_youtube(
                video_file=video_file,
                pkg=pkg,
                privacy_status=args.privacy,
                output_dir=out_dir,
            )
            log(f"[{job_index}/{total_jobs}] Uploaded: https://www.youtube.com/watch?v={video_id}")
        except Exception as exc:
            error_file = out_dir / "youtube_upload_error.txt"
            error_file.write_text(str(exc).strip() + "\n", encoding="utf-8")
            log(
                f"[{job_index}/{total_jobs}] YouTube upload failed but pipeline will continue. "
                f"Reason: {exc}"
            )
    else:
        log(f"[{job_index}/{total_jobs}] Upload skipped.")
    return out_dir


def run_pipeline(args: argparse.Namespace) -> None:
    load_dotenv()
    root_output_dir = Path(args.output_root).resolve() if args.output_root else OUTPUTS_DIR
    ensure_dir(root_output_dir)

    llm = LLMClient()
    if args.upload_youtube:
        ok, reason = youtube_upload_preflight()
        if not ok:
            log(
                "YouTube upload disabled for this run: "
                f"{reason} Videos will still be fully generated."
            )
            args.upload_youtube = False

    used_topics: set[str] = set()
    outputs: list[str] = []
    total_jobs = max(1, args.batch)

    for i in range(1, total_jobs + 1):
        topic_override = args.topic if (args.topic and i == 1) else None
        out_dir = run_single_job(
            args=args,
            llm=llm,
            root_output_dir=root_output_dir,
            used_topics=used_topics,
            topic_override=topic_override,
            job_index=i,
            total_jobs=total_jobs,
        )
        outputs.append(str(out_dir))
        if i < total_jobs and args.sleep_seconds > 0:
            log(f"Sleeping {args.sleep_seconds}s before next job...")
            time.sleep(args.sleep_seconds)

    summary = {
        "timestamp": datetime.now().isoformat(),
        "batch_size": total_jobs,
        "niche": args.niche,
        "format": args.format,
        "outputs": outputs,
    }
    summary_file = root_output_dir / f"batch_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(f"All jobs complete. Batch summary: {summary_file}")


def install_windows_task(args: argparse.Namespace) -> None:
    python_exe = Path(sys.executable).resolve()
    script_path = Path(__file__).resolve()
    working_dir = script_path.parent
    command = (
        f'"{python_exe}" "{script_path}" run '
        f'--niche "{args.niche}" --audience "{args.audience}" '
        f'--format {args.format} --duration {args.duration} --images {args.images} '
        f'--batch {args.batch} --sleep-seconds {args.sleep_seconds}'
    )
    if args.upload_youtube:
        command += f" --upload-youtube --privacy {args.privacy}"
    if args.no_captions:
        command += " --no-captions"

    tr = f'cmd /c "cd /d {working_dir} && {command}"'
    task_name = args.task_name

    create_cmd = [
        "schtasks",
        "/Create",
        "/SC",
        "DAILY",
        "/TN",
        task_name,
        "/TR",
        tr,
        "/ST",
        args.time,
        "/F",
    ]
    run_cmd(create_cmd)
    log(f'Scheduled task "{task_name}" created for {args.time} daily.')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Autonomous faceless content studio: topic -> script -> voice -> video -> optional YouTube upload."
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run one full autonomous content job.")
    run_parser.add_argument("--topic", type=str, default=None, help="Optional fixed topic.")
    run_parser.add_argument("--niche", type=str, default=os.getenv("DEFAULT_NICHE", "personal finance"))
    run_parser.add_argument(
        "--audience",
        type=str,
        default=os.getenv("DEFAULT_AUDIENCE", "English-speaking adults in US/UK/CA"),
    )
    run_parser.add_argument(
        "--format",
        type=str,
        choices=["short", "long"],
        default=os.getenv("DEFAULT_FORMAT", "short"),
        help="short = 9:16 (Shorts/Reels), long = 16:9",
    )
    run_parser.add_argument(
        "--duration",
        type=int,
        default=int(os.getenv("DEFAULT_DURATION_SECONDS", "55")),
        help="Target script duration in seconds.",
    )
    run_parser.add_argument(
        "--images",
        type=int,
        default=int(os.getenv("DEFAULT_IMAGE_COUNT", "8")),
        help="Target number of b-roll images.",
    )
    run_parser.add_argument(
        "--batch",
        type=int,
        default=int(os.getenv("DEFAULT_BATCH_SIZE", "1")),
        help="How many autonomous videos to produce in one run.",
    )
    run_parser.add_argument(
        "--sleep-seconds",
        type=int,
        default=int(os.getenv("DEFAULT_BATCH_SLEEP_SECONDS", "3")),
        help="Delay between jobs in batch mode.",
    )
    run_parser.add_argument(
        "--geo",
        type=str,
        default=os.getenv("TRENDS_GEO", "US"),
        help="Geo used for Google Trends topic hints.",
    )
    run_parser.add_argument("--upload-youtube", action="store_true", help="Upload output video to YouTube.")
    run_parser.add_argument(
        "--privacy",
        type=str,
        choices=["private", "unlisted", "public"],
        default=os.getenv("YOUTUBE_DEFAULT_PRIVACY", "private"),
    )
    run_parser.add_argument("--no-captions", action="store_true", help="Skip subtitle generation/burn.")
    run_parser.add_argument("--dry-run", action="store_true", help="Only generate package files, no media rendering.")
    run_parser.add_argument(
        "--output-root",
        type=str,
        default=str(OUTPUTS_DIR),
        help="Root folder for generated jobs.",
    )

    task_parser = subparsers.add_parser(
        "install-task", help="Create a Windows scheduled task for daily autonomous runs."
    )
    task_parser.add_argument("--task-name", type=str, default="FacelessAutoStudio")
    task_parser.add_argument("--time", type=str, default="09:00", help="24h time HH:MM")
    task_parser.add_argument("--niche", type=str, default=os.getenv("DEFAULT_NICHE", "personal finance"))
    task_parser.add_argument(
        "--audience",
        type=str,
        default=os.getenv("DEFAULT_AUDIENCE", "English-speaking adults in US/UK/CA"),
    )
    task_parser.add_argument("--format", type=str, choices=["short", "long"], default=os.getenv("DEFAULT_FORMAT", "short"))
    task_parser.add_argument("--duration", type=int, default=int(os.getenv("DEFAULT_DURATION_SECONDS", "55")))
    task_parser.add_argument("--images", type=int, default=int(os.getenv("DEFAULT_IMAGE_COUNT", "8")))
    task_parser.add_argument("--batch", type=int, default=int(os.getenv("DEFAULT_BATCH_SIZE", "1")))
    task_parser.add_argument("--sleep-seconds", type=int, default=int(os.getenv("DEFAULT_BATCH_SLEEP_SECONDS", "3")))
    task_parser.add_argument("--upload-youtube", action="store_true")
    task_parser.add_argument("--privacy", type=str, choices=["private", "unlisted", "public"], default="private")
    task_parser.add_argument("--no-captions", action="store_true")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        # Default behavior for convenience.
        args = parser.parse_args(["run"])

    start = time.time()
    if args.command == "run":
        run_pipeline(args)
    elif args.command == "install-task":
        install_windows_task(args)
    else:
        parser.print_help()
        sys.exit(1)
    elapsed = time.time() - start
    log(f"Finished in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
