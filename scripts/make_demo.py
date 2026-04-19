#!/usr/bin/env python3
"""
Demo video production for Subprime / Benji AI Financial Advisor.

Produces two MP4s:
  finadvisor-demo-product.mp4   — product-only, 15-25s, happy music
  finadvisor-demo-research.mp4  — research + product interleaved, 20-30s, music shifts

Run:
  uv run python scripts/make_demo.py

Requires: ffmpeg, playwright, numpy, pillow
Server must be running:
  uv run uvicorn "apps.web.main:create_app" --factory --host 0.0.0.0 --port 8000
"""

import os
import math
import shutil
import struct
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright, Page

# ── Config ─────────────────────────────────────────────────────────────────────

BASE_URL = "http://localhost:8000"
OUTPUT_DIR = Path(__file__).parent.parent
ASSET_DIR = Path(__file__).parent / "demo_assets"
ASSET_DIR.mkdir(exist_ok=True)

W, H = 390, 844          # iPhone Pro mobile viewport
FPS = 24
FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_REG  = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

# Research stat cards — what to flash in video 2
STAT_CARDS = [
    {
        "headline": "5 models\n1,974 plans",
        "sub": "Claude · DeepSeek · GLM · Haiku · Llama",
        "bg": (15, 15, 25),
        "accent": (220, 50, 50),
    },
    {
        "headline": "APS shift:\n+0.07 → +0.24",
        "sub": "Hidden prompt. Quality score: unchanged.",
        "bg": (15, 15, 25),
        "accent": (220, 50, 50),
    },
    {
        "headline": "Cohen's d = 1.18",
        "sub": "Large effect size\nPQS spread < 0.03",
        "bg": (15, 15, 25),
        "accent": (220, 50, 50),
    },
    {
        "headline": "Dose-response:\n0.168 → 0.783",
        "sub": "Monotonic. The prompt is the bias.",
        "bg": (15, 15, 25),
        "accent": (220, 50, 50),
    },
]


# ── Music generation ────────────────────────────────────────────────────────────

def _write_wav(path: Path, samples: np.ndarray, sr: int = 44100) -> None:
    samples_int16 = (samples * 32767).astype(np.int16)
    with wave.open(str(path), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(samples_int16.tobytes())


def make_happy_music(duration: float, path: Path, sr: int = 44100) -> None:
    """Warm C-major chord progression, plucked feel — bright + optimistic."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    bpm = 112
    beat = sr * 60 / bpm

    def tone(freq, env_decay=0.3):
        wave_ = np.sin(2 * np.pi * freq * t)
        # pluck envelope: fast attack, exponential decay per note
        env = np.zeros_like(t)
        for onset in np.arange(0, len(t), beat):
            o = int(onset)
            decay_len = min(int(beat * 1.8), len(t) - o)
            env[o:o + decay_len] = np.exp(-np.linspace(0, env_decay * 10, decay_len))
        return wave_ * env

    # C major: C4 E4 G4 — then F major: F4 A4 C5 — repeating
    chord_c = tone(261.63) * 0.4 + tone(329.63) * 0.35 + tone(392.00) * 0.3
    chord_f = tone(349.23) * 0.4 + tone(440.00) * 0.35 + tone(523.25) * 0.3

    # Alternate every 2 beats
    two_beat = int(beat * 2)
    signal = np.zeros_like(t)
    for i in range(0, len(t), two_beat * 2):
        signal[i:i + two_beat] += chord_c[i:i + two_beat]
        signal[i + two_beat:i + two_beat * 2] += chord_f[i + two_beat:i + two_beat * 2]

    # Add a gentle high melody (E5 D5 C5 oscillation)
    melody_freqs = [659.25, 587.33, 523.25, 587.33]
    mel_beat = int(beat)
    for i, freq in enumerate(melody_freqs * (int(duration * bpm / 60 // 4) + 2)):
        start = i * mel_beat
        end = min(start + mel_beat, len(t))
        if start >= len(t):
            break
        seg = np.sin(2 * np.pi * freq * t[start:end])
        env = np.exp(-np.linspace(0, 4, end - start))
        signal[start:end] += seg * env * 0.15

    # Soft hi-hat noise every beat
    for onset in np.arange(0, len(t), beat):
        o = int(onset)
        n = min(int(sr * 0.03), len(t) - o)
        noise = np.random.randn(n) * np.exp(-np.linspace(0, 8, n)) * 0.05
        signal[o:o + n] += noise

    # Normalize + fade in/out
    signal /= np.max(np.abs(signal)) * 1.2
    fade = int(sr * 0.4)
    signal[:fade] *= np.linspace(0, 1, fade)
    signal[-fade:] *= np.linspace(1, 0, fade)

    _write_wav(path, signal, sr)
    print(f"  [music] happy → {path.name}")


def make_sinister_music(duration: float, path: Path, sr: int = 44100) -> None:
    """A-minor drone with descending bass, tension tremolo."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)

    # Low A drone (110 Hz) + dark fifths
    drone = np.sin(2 * np.pi * 110 * t) * 0.45
    drone += np.sin(2 * np.pi * 165 * t) * 0.2   # E2 (fifth)
    drone += np.sin(2 * np.pi * 130.81 * t) * 0.15  # C3 (minor third)

    # Tremolo (sinister wobble at 6 Hz)
    tremolo = 0.7 + 0.3 * np.sin(2 * np.pi * 6 * t)
    drone *= tremolo

    # Descending bass walk: A2 → G2 → F2 → E2 over the duration
    bass_notes = [110, 98, 87.31, 82.41]
    seg_len = len(t) // len(bass_notes)
    bass = np.zeros_like(t)
    for i, freq in enumerate(bass_notes):
        start = i * seg_len
        end = min(start + seg_len, len(t))
        bass[start:end] = np.sin(2 * np.pi * freq * t[start:end]) * 0.35

    # Occasional tense high string (D5 spike)
    string = np.sin(2 * np.pi * 587.33 * t) * 0.0
    for spike_t in [duration * 0.3, duration * 0.6, duration * 0.85]:
        o = int(spike_t * sr)
        n = min(int(sr * 0.8), len(t) - o)
        env = np.exp(-np.linspace(0, 3, n))
        string[o:o + n] += np.sin(2 * np.pi * 587.33 * t[o:o + n]) * env * 0.12

    signal = drone + bass + string
    signal /= np.max(np.abs(signal)) * 1.3
    fade = int(sr * 0.5)
    signal[:fade] *= np.linspace(0, 1, fade)
    signal[-fade:] *= np.linspace(1, 0, fade)

    _write_wav(path, signal, sr)
    print(f"  [music] sinister → {path.name}")


# ── Stat card generation ────────────────────────────────────────────────────────

def make_stat_card(card: dict, path: Path) -> None:
    img = Image.new("RGB", (W, H), color=card["bg"])
    draw = ImageDraw.Draw(img)

    # Red accent bar at top
    bar_h = 6
    draw.rectangle([0, 0, W, bar_h], fill=card["accent"])

    # Center content vertically
    try:
        font_big = ImageFont.truetype(FONT_BOLD, 42)
        font_sub = ImageFont.truetype(FONT_REG, 22)
        font_label = ImageFont.truetype(FONT_REG, 16)
    except Exception:
        font_big = ImageFont.load_default()
        font_sub = font_big
        font_label = font_big

    # Label
    label = "SUBPRIME RESEARCH"
    draw.text((W // 2, H // 2 - 140), label, font=font_label,
              fill=(180, 60, 60), anchor="mm")

    # Thin divider
    draw.line([(W // 2 - 80, H // 2 - 110), (W // 2 + 80, H // 2 - 110)],
              fill=(80, 80, 100), width=1)

    # Headline — wrap if needed
    headline = card["headline"]
    # Split on · or — for line breaks
    parts = headline.replace(" · ", "\n").replace(" — ", "\n")
    draw.text((W // 2, H // 2 - 30), parts, font=font_big,
              fill=(240, 240, 255), anchor="mm", align="center")

    # Sub text — shrink font until it fits within margins
    sub_text = card["sub"]
    margin = 24
    max_w = W - margin * 2
    sub_size = 22
    while sub_size > 10:
        font_sub_fit = ImageFont.truetype(FONT_REG, sub_size)
        # measure widest line
        widest = max(
            draw.textlength(line, font=font_sub_fit)
            for line in sub_text.split("\n")
        )
        if widest <= max_w:
            break
        sub_size -= 1
    else:
        font_sub_fit = ImageFont.truetype(FONT_REG, 10)
    draw.text((W // 2, H // 2 + 80), sub_text, font=font_sub_fit,
              fill=(160, 160, 190), anchor="mm", align="center")

    # Bottom bar
    draw.rectangle([0, H - bar_h, W, H], fill=card["accent"])

    img.save(str(path))
    print(f"  [card] {path.name}")


# ── Playwright capture ──────────────────────────────────────────────────────────

class AppRecorder:
    def __init__(self, page: Page):
        self.page = page
        self.frames: list[Path] = []
        self._frame_idx = 0

    def _snap(self, tag: str = "") -> Path:
        p = ASSET_DIR / f"frame_{self._frame_idx:04d}_{tag}.png"
        self.page.screenshot(path=str(p), full_page=False)
        self.frames.append(p)
        self._frame_idx += 1
        return p

    def _hold(self, seconds: float, tag: str = "hold"):
        """Repeat last screenshot for N seconds worth of frames."""
        n = max(1, int(seconds * FPS))
        last = self.frames[-1] if self.frames else None
        for i in range(n):
            p = ASSET_DIR / f"frame_{self._frame_idx:04d}_{tag}_{i}.png"
            if last:
                shutil.copy(last, p)
            else:
                Image.new("RGB", (W, H), (10, 10, 20)).save(str(p))
            self.frames.append(p)
            self._frame_idx += 1

    def _insert(self, img_path: Path, seconds: float, tag: str = "card"):
        n = max(1, int(seconds * FPS))
        for i in range(n):
            p = ASSET_DIR / f"frame_{self._frame_idx:04d}_{tag}_{i}.png"
            shutil.copy(img_path, p)
            self.frames.append(p)
            self._frame_idx += 1

    def capture_product_flow(self):
        """Navigate and capture the full Benji product demo flow."""
        p = self.page

        # Step 1 — landing (plan tier selection)
        print("  [capture] step 1: landing")
        p.goto(BASE_URL, wait_until="networkidle")
        # Wait for the "Start Free Plan" button
        p.wait_for_selector("button[data-tier='basic']", timeout=10000)
        self._snap("step1_landing")
        self._hold(1.2)

        # Click "Start Free Plan" — HTMX posts then redirects via HX-Redirect header
        with p.expect_response("**/api/select-tier"):
            p.click("button[data-tier='basic']")
        p.wait_for_url("**/step/2", timeout=8000)
        p.wait_for_load_state("networkidle")
        self._snap("step2_enter")
        self._hold(0.5)

        # Step 2 — persona selection
        print("  [capture] step 2: persona")
        # Persona cards are buttons with hx-post="/api/select-persona"
        p.wait_for_selector("button[hx-post='/api/select-persona']", timeout=10000)
        self._snap("step2_personas")
        self._hold(1.0)

        # Pick Hermione Granger — mid-career, complex goals
        hermione = p.locator("button[hx-post='/api/select-persona']", has_text="Hermione").first
        hermione.scroll_into_view_if_needed()
        self._snap("step2_hermione_visible")
        self._hold(0.5)
        with p.expect_response("**/api/select-persona"):
            hermione.click()
        p.wait_for_url("**/step/3", timeout=8000)
        p.wait_for_load_state("networkidle")
        self._snap("step3_enter")
        self._hold(0.8)

        # Step 3 — strategy display + Generate Plan CTA
        # The strategy content loads via HTMX hx-trigger="load" → /api/generate-strategy
        # which returns the strategy_dashboard partial containing #generate-plan-btn
        print("  [capture] step 3: strategy (waiting for HTMX strategy load...)")
        # First capture the loading spinner state
        self._snap("step3_loading")
        self._hold(0.6)

        # Wait for #generate-plan-btn to appear (strategy generation completes — Together AI ~30-60s)
        p.wait_for_selector("#generate-plan-btn", timeout=120000)
        time.sleep(0.3)
        self._snap("step3_strategy")
        self._hold(1.5)

        # Scroll down to find Generate Plan button
        generate_btn = p.locator("#generate-plan-btn")
        generate_btn.scroll_into_view_if_needed()
        time.sleep(0.2)
        self._snap("step3_generate_visible")
        self._hold(0.8)
        generate_btn.click()

        # Step 4 — wait for plan generation (Together AI DeepSeek, ~30s without refinement)
        print("  [capture] step 4: generating plan (~30s)...")
        # Show loading state — the button is disabled and a progress bar appears
        time.sleep(1.5)
        try:
            p.wait_for_selector("#plan-loading:not(.hidden)", timeout=5000)
            self._snap("step4_loading")
            self._hold(1.0)
        except Exception:
            pass

        # HTMX: after API completes, it reads HX-Redirect and does window.location = "/step/4"
        # wait_for_navigation catches this JS-initiated navigation
        with p.expect_navigation(url="**/step/4", timeout=90000, wait_until="domcontentloaded"):
            pass  # navigation triggered by HTMX after plan generation completes
        p.wait_for_load_state("networkidle", timeout=15000)
        self._snap("step4_plan_top")
        self._hold(2.0)

        # Scroll partway down to show fund allocations
        p.evaluate("window.scrollBy(0, 350)")
        time.sleep(0.4)
        self._snap("step4_plan_mid")
        self._hold(1.8)

        # Scroll more to show rationale text
        p.evaluate("window.scrollBy(0, 350)")
        time.sleep(0.4)
        self._snap("step4_plan_lower")
        self._hold(2.5)

        return self.frames[:]


# ── Frame → video ───────────────────────────────────────────────────────────────

def frames_to_video(frames: list[Path], output: Path, music: Path,
                    music_volume: float = 0.7) -> None:
    """Assemble frames into MP4 with music, using FFmpeg concat."""
    if not frames:
        raise ValueError("No frames to encode")

    # Write a file list for ffmpeg concat demuxer
    list_path = ASSET_DIR / "framelist.txt"
    with open(list_path, "w") as f:
        for i, frame in enumerate(frames):
            duration = 1.0 / FPS
            f.write(f"file '{frame.resolve()}'\n")
            f.write(f"duration {duration:.6f}\n")
        # Repeat last frame (ffmpeg concat needs it)
        f.write(f"file '{frames[-1].resolve()}'\n")

    total_duration = len(frames) / FPS

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-i", str(music),
        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-filter_complex", f"[1:a]volume={music_volume},afade=t=out:st={total_duration-1}:d=1[a]",
        "-map", "0:v", "-map", "[a]",
        "-t", str(total_duration),
        "-movflags", "+faststart",
        str(output),
    ]
    print(f"  [ffmpeg] encoding {output.name} ({total_duration:.1f}s, {len(frames)} frames)")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFmpeg stderr:", result.stderr[-2000:])
        raise RuntimeError(f"FFmpeg failed: {result.returncode}")
    print(f"  [done] {output} ({output.stat().st_size // 1024}KB)")


def crossfade(a: Path, b: Path, duration: float = 0.4) -> tuple[str, str]:
    """Return ffmpeg filtergraph strings for crossfade between two image inputs."""
    # For concat-based video this is applied at the image level (pre-encode).
    # We do a simple PIL blend here instead.
    return "", ""


def blend_images(a: Path, b: Path, alpha: float) -> Image.Image:
    ia = Image.open(a).convert("RGBA")
    ib = Image.open(b).convert("RGBA")
    if ia.size != ib.size:
        ib = ib.resize(ia.size, Image.LANCZOS)
    return Image.blend(ia, ib, alpha).convert("RGB")


def insert_crossfade(frames: list[Path], idx: int, n_frames: int = 8) -> list[Path]:
    """Insert n_frames crossfade transition around index idx in frames list."""
    if idx <= 0 or idx >= len(frames):
        return frames
    before = frames[idx - 1]
    after = frames[idx]
    transition_frames = []
    for i in range(n_frames):
        alpha = i / n_frames
        blended = blend_images(before, after, alpha)
        p = ASSET_DIR / f"xfade_{idx:04d}_{i:02d}.png"
        blended.save(str(p))
        transition_frames.append(p)
    return frames[:idx] + transition_frames + frames[idx:]


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    print("=== Subprime Demo Video Production ===\n")

    # 1. Generate music tracks
    print("[1/4] Generating music tracks...")
    happy_wav = ASSET_DIR / "music_happy.wav"
    sinister_wav = ASSET_DIR / "music_sinister.wav"
    make_happy_music(35.0, happy_wav)
    make_sinister_music(35.0, sinister_wav)

    # 2. Generate research stat cards
    print("\n[2/4] Generating research stat cards...")
    card_paths = []
    for i, card in enumerate(STAT_CARDS):
        p = ASSET_DIR / f"stat_card_{i}.png"
        make_stat_card(card, p)
        card_paths.append(p)

    # 3. Capture app flow via Playwright
    print("\n[3/4] Capturing app flow with Playwright...")
    recorder = AppRecorder.__new__(AppRecorder)
    recorder.frames = []
    recorder._frame_idx = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": W, "height": H},
            device_scale_factor=1,
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            ),
        )
        page = ctx.new_page()
        recorder.page = page
        product_frames = recorder.capture_product_flow()
        browser.close()

    print(f"  [captured] {len(product_frames)} product frames")

    # 4. Assemble videos
    print("\n[4/4] Assembling videos...")

    # ── Video 1: Product only ──────────────────────────────────────────────────
    # Add crossfades at key transition points (every ~12 frames / 0.5s)
    pframes = product_frames[:]

    # Find rough transition boundaries (between steps)
    transitions = []
    for i, f in enumerate(pframes):
        name = f.name
        if "step2_enter" in name or "step3_after" in name or "step4_plan_top" in name:
            transitions.append(i)

    offset = 0
    for idx in transitions:
        pframes = insert_crossfade(pframes, idx + offset)
        offset += 8  # crossfade inserts 8 new frames

    v1_out = OUTPUT_DIR / "finadvisor-demo-product.mp4"
    frames_to_video(pframes, v1_out, happy_wav, music_volume=0.75)
    shutil.copy(v1_out, OUTPUT_DIR / "apps/web/static/finadvisor-demo-product.mp4")

    # ── Video 2: Research + Product interleaved ────────────────────────────────
    # Structure: stat card → product clip → stat card → product clip → ...
    # Music: sinister during cards, happy during product
    #
    # We'll create two separate audio tracks and mix them.

    r2_frames: list[Path] = []
    r2_music_segments = []  # list of (start_frame, end_frame, track)

    def r2_add_card(card_path: Path, hold_s: float, with_xfade: bool = True):
        start = len(r2_frames)
        n = int(hold_s * FPS)
        for i in range(n):
            p = ASSET_DIR / f"r2_card_{len(r2_frames):04d}.png"
            shutil.copy(card_path, p)
            r2_frames.append(p)
        r2_music_segments.append((start, len(r2_frames), "sinister"))

    def r2_add_product(src_frames: list[Path], with_xfade: bool = True):
        start = len(r2_frames)
        r2_frames.extend(src_frames)
        r2_music_segments.append((start, len(r2_frames), "happy"))

    # Interleaving plan for ~25s video
    # Frame counts at 24fps:
    #   card: 1.8s = 43 frames
    #   product clip: variable
    step1_frames = [f for f in product_frames if "step1" in f.name or "step2_enter" in f.name]
    step2_frames = [f for f in product_frames if "step2_personas" in f.name or "step2_hermione" in f.name]
    step3_frames = [f for f in product_frames if "step3" in f.name]
    step4_frames = [f for f in product_frames if "step4" in f.name]

    # Extend each clip's hold to fill time
    def extend(frames: list[Path], target_s: float) -> list[Path]:
        target_n = int(target_s * FPS)
        if len(frames) >= target_n:
            return frames[:target_n]
        extra = target_n - len(frames)
        last = frames[-1] if frames else card_paths[0]
        copies = []
        for i in range(extra):
            p = ASSET_DIR / f"ext_{len(r2_frames)+len(copies):04d}.png"
            shutil.copy(last, p)
            copies.append(p)
        return frames + copies

    # Stat card 0 → product clip → card 1 → product → card 2 → product → card 3 → end
    r2_add_card(card_paths[0], hold_s=2.2)
    r2_add_product(extend(step1_frames or step2_frames[:6], 2.5))
    r2_add_card(card_paths[1], hold_s=2.2)
    r2_add_product(extend(step2_frames, 3.0))
    r2_add_card(card_paths[2], hold_s=2.2)
    r2_add_product(extend(step3_frames, 2.5))
    r2_add_card(card_paths[3], hold_s=2.2)
    r2_add_product(extend(step4_frames, 4.0))

    # Insert crossfades at every segment boundary
    boundaries = []
    pos = 0
    prev_track = None
    for start, end, track in r2_music_segments:
        if prev_track is not None and pos > 0:
            boundaries.append(pos)
        pos = end
        prev_track = track

    xoffset = 0
    for b in boundaries:
        r2_frames = insert_crossfade(r2_frames, b + xoffset)
        xoffset += 8

    # Build a mixed audio track: sinister during cards, happy during product
    # Use FFmpeg amix with volume automation via azmq or just mix both at appropriate levels
    total_frames = len(r2_frames)
    total_s = total_frames / FPS

    # Build per-frame audio mask: 1.0 = sinister dominant, 0.0 = happy dominant
    sinister_mask = np.zeros(total_frames)
    happy_mask = np.zeros(total_frames)
    for start, end, track in r2_music_segments:
        end = min(end, total_frames)
        if track == "sinister":
            sinister_mask[start:end] = 1.0
        else:
            happy_mask[start:end] = 1.0

    # Smooth transitions (12-frame crossfade)
    from scipy.ndimage import uniform_filter1d
    sinister_mask = uniform_filter1d(sinister_mask.astype(float), size=12)
    happy_mask = uniform_filter1d(happy_mask.astype(float), size=12)

    # Load both WAV files and apply masks
    sr = 44100

    def load_wav(path: Path) -> np.ndarray:
        with wave.open(str(path), "r") as f:
            frames_data = f.readframes(f.getnframes())
            arr = np.frombuffer(frames_data, dtype=np.int16).astype(np.float32) / 32767.0
        return arr

    happy_audio = load_wav(happy_wav)
    sinister_audio = load_wav(sinister_wav)

    # Interpolate masks to audio sample count
    audio_len = int(total_s * sr)
    xs = np.linspace(0, 1, total_frames)
    xa = np.linspace(0, 1, audio_len)
    s_mask_audio = np.interp(xa, xs, sinister_mask[:total_frames])
    h_mask_audio = np.interp(xa, xs, happy_mask[:total_frames])

    min_len = min(audio_len, len(happy_audio), len(sinister_audio))
    mixed = (
        sinister_audio[:min_len] * s_mask_audio[:min_len] * 0.8
        + happy_audio[:min_len] * h_mask_audio[:min_len] * 0.75
    )
    mx = np.max(np.abs(mixed))
    if mx > 0:
        mixed /= mx * 1.1
    fade = int(sr * 0.5)
    mixed[:fade] *= np.linspace(0, 1, fade)
    mixed[-fade:] *= np.linspace(1, 0, fade)

    mixed_wav = ASSET_DIR / "music_mixed.wav"
    _write_wav(mixed_wav, mixed, sr)

    v2_out = OUTPUT_DIR / "finadvisor-demo-research.mp4"
    frames_to_video(r2_frames, v2_out, mixed_wav, music_volume=1.0)
    shutil.copy(v2_out, OUTPUT_DIR / "apps/web/static/finadvisor-demo-research.mp4")

    print(f"\n{'='*50}")
    print(f"Video 1 (product):  {v1_out}")
    print(f"Video 2 (research): {v2_out}")
    print(f"{'='*50}")
    print("\nReview with: python scripts/review_demo.py")


if __name__ == "__main__":
    main()
