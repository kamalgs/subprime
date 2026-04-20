#!/usr/bin/env python3
"""
Demo video production for Subprime / Benji (React SPA).

Produces two MP4s, both H.264 baseline / yuv420p / AAC — plays on every
OS and mobile browser without an HTML5 <source> fallback:

  product/finadvisor-demo.mp4   — full product flow, mobile viewport, ~25s
  research/finadvisor-demo.mp4  — 4 research stat cards (~10s) prepended to
                                   a truncated product clip (~12s), ~22s

Run:
    make frontend                               # build the SPA (dist/ must exist)
    uv run uvicorn "apps.web.main:create_app" --factory --host 0.0.0.0 --port 8000 &
    uv run python research/scripts/make_demo.py

Requires ffmpeg on PATH, plus playwright, numpy, pillow, scipy.
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import time
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import Page, sync_playwright

BASE_URL = os.environ.get("SUBPRIME_DEMO_URL", "http://localhost:8000")
REPO_ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = Path(__file__).resolve().parent / "demo_assets"
ASSET_DIR.mkdir(exist_ok=True)

W, H = 390, 844                 # iPhone 14 Pro viewport
FPS = 24
FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_REG  = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

STAT_CARDS = [
    {
        "headline": "5 models\n1,974 plans",
        "sub": "Claude · DeepSeek · GLM · Haiku · Llama",
    },
    {
        "headline": "APS shift\n+0.07 → +0.24",
        "sub": "Hidden prompt moves the advice.\nQuality score barely budges.",
    },
    {
        "headline": "Cohen's d = 1.18",
        "sub": "Large effect size\nPQS spread < 0.03",
    },
    {
        "headline": "Dose-response\n0.168 → 0.783",
        "sub": "Monotonic in prompt intensity.\nThe prompt is the bias.",
    },
]


# ── Music ──────────────────────────────────────────────────────────────────────

def _write_wav(path: Path, samples: np.ndarray, sr: int = 44100) -> None:
    pcm = (samples * 32767).astype(np.int16)
    with wave.open(str(path), "w") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
        f.writeframes(pcm.tobytes())


def make_happy_music(duration: float, path: Path, sr: int = 44100) -> None:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    bpm = 112; beat = sr * 60 / bpm

    def tone(freq):
        w = np.sin(2 * np.pi * freq * t)
        env = np.zeros_like(t)
        for onset in np.arange(0, len(t), beat):
            o = int(onset)
            n = min(int(beat * 1.8), len(t) - o)
            env[o:o + n] = np.exp(-np.linspace(0, 3, n))
        return w * env

    chord_c = tone(261.63) * 0.4 + tone(329.63) * 0.35 + tone(392.00) * 0.3
    chord_f = tone(349.23) * 0.4 + tone(440.00) * 0.35 + tone(523.25) * 0.3
    two = int(beat * 2)
    signal = np.zeros_like(t)
    for i in range(0, len(t), two * 2):
        signal[i:i + two] += chord_c[i:i + two]
        signal[i + two:i + two * 2] += chord_f[i + two:i + two * 2]

    mel = [659.25, 587.33, 523.25, 587.33]
    mb = int(beat)
    for i, f in enumerate(mel * (int(duration * bpm / 60 // 4) + 2)):
        s = i * mb; e = min(s + mb, len(t))
        if s >= len(t): break
        signal[s:e] += np.sin(2 * np.pi * f * t[s:e]) * np.exp(-np.linspace(0, 4, e - s)) * 0.15

    signal /= np.max(np.abs(signal)) * 1.2
    fade = int(sr * 0.4)
    signal[:fade] *= np.linspace(0, 1, fade)
    signal[-fade:] *= np.linspace(1, 0, fade)
    _write_wav(path, signal, sr)


def make_sinister_music(duration: float, path: Path, sr: int = 44100) -> None:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    drone = np.sin(2 * np.pi * 110 * t) * 0.45
    drone += np.sin(2 * np.pi * 165 * t) * 0.2
    drone += np.sin(2 * np.pi * 130.81 * t) * 0.15
    drone *= 0.7 + 0.3 * np.sin(2 * np.pi * 6 * t)

    bass = np.zeros_like(t)
    notes = [110, 98, 87.31, 82.41]
    seg = len(t) // len(notes)
    for i, f in enumerate(notes):
        s = i * seg; e = min(s + seg, len(t))
        bass[s:e] = np.sin(2 * np.pi * f * t[s:e]) * 0.35

    signal = drone + bass
    signal /= np.max(np.abs(signal)) * 1.3
    fade = int(sr * 0.5)
    signal[:fade] *= np.linspace(0, 1, fade)
    signal[-fade:] *= np.linspace(1, 0, fade)
    _write_wav(path, signal, sr)


# ── Stat cards ─────────────────────────────────────────────────────────────────

def make_stat_card(card: dict, path: Path) -> None:
    img = Image.new("RGB", (W, H), color=(15, 15, 25))
    draw = ImageDraw.Draw(img)
    accent = (220, 50, 50)
    draw.rectangle([0, 0, W, 6], fill=accent)
    draw.rectangle([0, H - 6, W, H], fill=accent)

    try:
        font_big = ImageFont.truetype(FONT_BOLD, 44)
        font_sub = ImageFont.truetype(FONT_REG, 22)
        font_label = ImageFont.truetype(FONT_REG, 14)
    except Exception:
        font_big = font_sub = font_label = ImageFont.load_default()

    draw.text((W // 2, H // 2 - 150), "SUBPRIME · RESEARCH",
              font=font_label, fill=(180, 60, 60), anchor="mm")
    draw.line([(W // 2 - 90, H // 2 - 120), (W // 2 + 90, H // 2 - 120)],
              fill=(80, 80, 100), width=1)
    draw.text((W // 2, H // 2 - 30), card["headline"],
              font=font_big, fill=(240, 240, 255), anchor="mm", align="center")

    sub = card["sub"]
    size = 22
    while size > 12:
        f = ImageFont.truetype(FONT_REG, size)
        widest = max(draw.textlength(line, font=f) for line in sub.split("\n"))
        if widest <= W - 48:
            break
        size -= 1
    draw.text((W // 2, H // 2 + 90), sub,
              font=ImageFont.truetype(FONT_REG, size),
              fill=(160, 160, 190), anchor="mm", align="center")

    img.save(str(path))


# ── Playwright capture ─────────────────────────────────────────────────────────

class AppRecorder:
    def __init__(self, page: Page):
        self.page = page
        self.frames: list[Path] = []
        self._idx = 0

    def _snap(self, tag: str) -> Path:
        p = ASSET_DIR / f"frame_{self._idx:04d}_{tag}.png"
        self.page.screenshot(path=str(p), full_page=False)
        self.frames.append(p); self._idx += 1
        return p

    def _hold(self, seconds: float, tag: str = "hold"):
        n = max(1, int(seconds * FPS))
        last = self.frames[-1]
        for i in range(n):
            p = ASSET_DIR / f"frame_{self._idx:04d}_{tag}_{i}.png"
            shutil.copy(last, p)
            self.frames.append(p); self._idx += 1

    def _dismiss_sebi(self):
        """Dismiss the SEBI modal if it pops up — cookie approach is fragile
        across subdomains, so we just click the button when visible."""
        try:
            self.page.wait_for_selector("text=I understand", timeout=5_000)
            self.page.click("text=I understand")
            self.page.wait_for_selector("text=I understand",
                                        state="detached", timeout=3_000)
        except Exception:
            pass  # modal already dismissed or not shown

    def capture(self) -> list[Path]:
        p = self.page

        # Step 1 — landing (tier choice)
        print("  [capture] step 1: landing")
        p.goto(BASE_URL, wait_until="networkidle")
        self._dismiss_sebi()
        p.wait_for_selector("text=Choose your plan", timeout=10_000)
        self._snap("step1"); self._hold(1.3, "step1")

        # "Start free plan" is the basic-tier CTA
        p.click("text=Start free plan")
        p.wait_for_selector("text=Your investor profile", timeout=10_000)
        self._snap("step2_enter"); self._hold(0.5, "step2a")

        # Step 2 — persona archetype (Basic tier shows 3 cards)
        print("  [capture] step 2: persona archetype")
        p.wait_for_selector("text=Mid career", timeout=5_000)
        self._snap("step2_personas"); self._hold(1.1, "step2b")

        persona = p.locator("button", has_text="Mid career").first
        persona.scroll_into_view_if_needed()
        self._snap("step2_focus"); self._hold(0.5, "step2c")
        persona.click()
        time.sleep(0.3)

        # Archetype pre-fills everything except the name — provide one.
        name_input = p.locator("input[placeholder*='Ravi']").first
        name_input.fill("Ananya Shetty")
        self._snap("step2_filled"); self._hold(0.9, "step2d")

        # Submit the profile form — navigates to step 3 (strategy).
        p.click("text=Build my plan")
        p.wait_for_url("**/step/3", timeout=15_000)
        p.wait_for_load_state("networkidle")

        # Step 3 — strategy review + "Generate plan" CTA
        print("  [capture] step 3: strategy")
        self._snap("step3_loading"); self._hold(0.7, "step3a")
        # Strategy API is slow on cold path (Together AI); give it plenty.
        p.wait_for_selector("button:has-text('Generate my plan')", timeout=180_000)
        time.sleep(0.4)
        self._snap("step3_strategy"); self._hold(1.5, "step3b")
        p.click("button:has-text('Generate my plan')")

        # Step 4 — plan loading then plan view
        print("  [capture] step 4: plan (may be slow)")
        # Capture the loading state briefly
        time.sleep(1.0)
        self._snap("step4_loading"); self._hold(1.0, "step4a")

        # Allocations section appears when the plan has loaded. The React
        # route is /step/4; wait for the section header.
        p.wait_for_url("**/step/4", timeout=240_000)
        p.wait_for_selector("text=Allocation", timeout=240_000)
        time.sleep(0.6)
        self._snap("step4_top"); self._hold(2.0, "step4b")
        p.evaluate("window.scrollBy(0, 400)")
        time.sleep(0.3)
        self._snap("step4_mid"); self._hold(1.8, "step4c")
        p.evaluate("window.scrollBy(0, 400)")
        time.sleep(0.3)
        self._snap("step4_lower"); self._hold(2.4, "step4d")

        return self.frames[:]


# ── Video assembly ─────────────────────────────────────────────────────────────

def frames_to_video(frames: list[Path], output: Path, music: Path) -> None:
    if not frames:
        raise ValueError("no frames")
    listf = ASSET_DIR / f"list_{output.stem}.txt"
    with open(listf, "w") as f:
        for fr in frames:
            f.write(f"file '{fr.resolve()}'\n")
            f.write(f"duration {1.0 / FPS:.6f}\n")
        f.write(f"file '{frames[-1].resolve()}'\n")
    total = len(frames) / FPS

    # H.264 baseline profile + yuv420p + faststart = universal playback
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(listf),
        "-i", str(music),
        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H},format=yuv420p",
        "-c:v", "libx264",
        "-profile:v", "baseline", "-level", "3.1",
        "-preset", "slow", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-af", f"afade=t=out:st={max(0.1, total - 1):.2f}:d=1",
        "-t", str(total),
        "-movflags", "+faststart",
        str(output),
    ]
    print(f"  [ffmpeg] {output.name} ({total:.1f}s, {len(frames)} frames)")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        raise RuntimeError(f"ffmpeg exit {r.returncode}")
    print(f"  [done] {output}  {output.stat().st_size // 1024}KB")


def blend(a: Path, b: Path, alpha: float) -> Image.Image:
    ia = Image.open(a).convert("RGB")
    ib = Image.open(b).convert("RGB").resize(ia.size, Image.LANCZOS)
    return Image.blend(ia, ib, alpha)


def insert_xfade(frames: list[Path], idx: int, n: int = 8) -> list[Path]:
    if idx <= 0 or idx >= len(frames):
        return frames
    out = frames[:idx]
    for i in range(n):
        p = ASSET_DIR / f"xf_{idx:04d}_{i:02d}.png"
        blend(frames[idx - 1], frames[idx], (i + 1) / (n + 1)).save(str(p))
        out.append(p)
    out.extend(frames[idx:])
    return out


def card_frames(card_png: Path, seconds: float) -> list[Path]:
    n = int(seconds * FPS)
    out: list[Path] = []
    for i in range(n):
        p = ASSET_DIR / f"card_{card_png.stem}_{i:04d}.png"
        shutil.copy(card_png, p)
        out.append(p)
    return out


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=== Subprime Demo Production ===\n")

    print("[1/4] music tracks")
    happy = ASSET_DIR / "music_happy.wav"
    sinister = ASSET_DIR / "music_sinister.wav"
    make_happy_music(40, happy)
    make_sinister_music(14, sinister)

    print("[2/4] stat cards")
    cards: list[Path] = []
    for i, c in enumerate(STAT_CARDS):
        p = ASSET_DIR / f"card_{i}.png"
        make_stat_card(c, p)
        cards.append(p)

    print("[3/4] playwright capture (mobile viewport)")
    recorder = AppRecorder.__new__(AppRecorder)
    recorder.frames = []; recorder._idx = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": W, "height": H},
            device_scale_factor=2,
            user_agent=("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                        "Mobile/15E148 Safari/604.1"),
            is_mobile=True, has_touch=True,
        )
        recorder.page = ctx.new_page()
        product_frames = recorder.capture()
        browser.close()
    print(f"  [captured] {len(product_frames)} frames "
          f"({len(product_frames) / FPS:.1f}s)")

    print("[4/4] assemble videos")

    # ── Video 1: product only ──────────────────────────────────────────────
    pframes = product_frames[:]
    # Mild crossfade at major transitions to smooth the cut
    fade_tags = ("step2_enter", "step3_strategy", "step4_top")
    offset = 0
    for i in range(1, len(pframes)):
        if any(tag in pframes[i].name for tag in fade_tags):
            pframes = insert_xfade(pframes, i + offset, n=6)
            offset += 6

    product_out = REPO_ROOT / "product" / "finadvisor-demo.mp4"
    frames_to_video(pframes, product_out, happy)

    # ── Video 2: research cards (~10s) + truncated product clip (~12s) ─────
    r_frames: list[Path] = []
    for card in cards:
        r_frames.extend(card_frames(card, 2.5))
        # crossfade into the next card
        r_frames = insert_xfade(r_frames, len(r_frames), n=6) \
            if len(r_frames) > 0 else r_frames

    # Pick an evocative slice of the product flow — first ~12s after step2
    # (persona selected) through the first plan view. Helps viewers see
    # *what* "the prompt" was influencing.
    product_slice_start = 0
    for i, f in enumerate(product_frames):
        if "step2_personas" in f.name:
            product_slice_start = i; break
    product_slice = product_frames[product_slice_start:
                                   product_slice_start + int(12 * FPS)]
    r_frames.extend(product_slice)

    # Mixed music: sinister while cards play, happy during the product clip.
    from scipy.ndimage import uniform_filter1d
    total = len(r_frames)
    sin_mask = np.zeros(total); hap_mask = np.zeros(total)
    card_end = int(4 * 2.5 * FPS)   # 4 cards × 2.5s
    sin_mask[:card_end] = 1.0
    hap_mask[card_end:] = 1.0
    sin_mask = uniform_filter1d(sin_mask, size=12)
    hap_mask = uniform_filter1d(hap_mask, size=12)

    def load_wav(p: Path) -> np.ndarray:
        with wave.open(str(p), "r") as f:
            return (np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
                    .astype(np.float32) / 32767.0)

    sr = 44100
    duration = total / FPS
    audio_len = int(duration * sr)
    xs = np.linspace(0, 1, total); xa = np.linspace(0, 1, audio_len)
    sma = np.interp(xa, xs, sin_mask); hma = np.interp(xa, xs, hap_mask)

    sa = load_wav(sinister); ha = load_wav(happy)
    # Tile / truncate to audio_len
    sa = np.tile(sa, math.ceil(audio_len / len(sa)))[:audio_len]
    ha = np.tile(ha, math.ceil(audio_len / len(ha)))[:audio_len]
    mixed = sa * sma * 0.75 + ha * hma * 0.80
    mx = np.max(np.abs(mixed))
    if mx > 0: mixed /= mx * 1.1
    fade_s = int(sr * 0.5)
    mixed[:fade_s] *= np.linspace(0, 1, fade_s)
    mixed[-fade_s:] *= np.linspace(1, 0, fade_s)
    mixed_wav = ASSET_DIR / "music_mixed.wav"
    _write_wav(mixed_wav, mixed, sr)

    research_out = REPO_ROOT / "research" / "finadvisor-demo.mp4"
    frames_to_video(r_frames, research_out, mixed_wav)

    print("\n" + "=" * 56)
    print(f"  product  → {product_out}")
    print(f"  research → {research_out}")
    print("=" * 56)


if __name__ == "__main__":
    main()
