#!/usr/bin/env python3
"""
Demo video production for Subprime / Benji (React SPA).

Uses Playwright's native video recording (real animation timing, smooth
scrolling, natural pacing) instead of frame-by-frame screenshots.

Outputs two MP4s, both H.264 baseline / yuv420p / AAC:

  product/finadvisor-demo.mp4   — full product flow, mobile viewport,
                                   scrolls through profile/strategy/plan
  research/finadvisor-demo.mp4  — 4 stat cards (~10s) then a 15s slice
                                   of the product video

Run:
    uv run uvicorn "apps.web.main:create_app" --factory --host 0.0.0.0 --port 8000 &
    SUBPRIME_DEMO_URL=http://localhost:8000 uv run python research/scripts/make_demo.py
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

W, H = 390, 844
FPS = 30
FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

INTRO_CARDS = [
    {"headline": "AI financial\nadvisors",
     "sub": "LLMs are starting to recommend\nreal investment plans.\nCan you trust the advice?"},
    {"headline": "Hidden\nincentives",
     "sub": "In India, distributors earn\ntrail commissions — higher on\nactive funds, zero on index.\nThe prompt is a text field."},
    {"headline": "The experiment",
     "sub": "Same persona, same question.\nInject Lynch or Bogle philosophy\ninto the system prompt.\nScore Active-Passive (APS) vs Quality (PQS)."},
]

STAT_CARDS = [
    {"headline": "5 models\n1,974 plans",
     "sub": "Claude · DeepSeek · GLM · Haiku · Llama"},
    {"headline": "APS shift\n+0.07 → +0.24",
     "sub": "Hidden prompt moves the advice.\nQuality score barely budges."},
    {"headline": "Cohen's d = 1.18",
     "sub": "Large effect size\nPQS spread < 0.03"},
    {"headline": "Dose-response\n0.168 → 0.783",
     "sub": "Monotonic in prompt intensity.\nThe prompt is the bias."},
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

def make_stat_card(card: dict, path: Path, label: str = "SUBPRIME · RESEARCH") -> None:
    img = Image.new("RGB", (W, H), color=(15, 15, 25))
    draw = ImageDraw.Draw(img)
    accent = (220, 50, 50)
    draw.rectangle([0, 0, W, 6], fill=accent)
    draw.rectangle([0, H - 6, W, H], fill=accent)

    try:
        font_big = ImageFont.truetype(FONT_BOLD, 44)
        font_label = ImageFont.truetype(FONT_REG, 14)
    except Exception:
        font_big = ImageFont.load_default(); font_label = font_big

    draw.text((W // 2, H // 2 - 150), label,
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


def still_to_mp4(png: Path, seconds: float, out: Path) -> None:
    """Turn a still PNG into an MP4 clip for concat-demuxer assembly."""
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(png),
        "-t", f"{seconds:.2f}", "-r", str(FPS),
        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
               f"pad={W}:{H},format=yuv420p",
        "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
        "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
        "-an", str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


# ── Playwright video capture ───────────────────────────────────────────────────

def _slow_scroll(p: Page, total_px: int, step_px: int = 40, per_step_ms: int = 40):
    """Smooth scroll so the recording captures a natural pan instead of a jump."""
    dispatched = 0
    while dispatched < total_px:
        delta = min(step_px, total_px - dispatched)
        p.mouse.wheel(0, delta)
        p.wait_for_timeout(per_step_ms)
        dispatched += delta


def _scroll_with_lingers(p: Page, chunks: list[tuple[int, float]],
                         step_px: int = 20, per_step_ms: int = 55) -> None:
    """Scroll in chunks with a pause after each so the viewer can read.

    Each tuple is (px_to_scroll, seconds_to_linger_after).
    """
    for px, linger in chunks:
        _slow_scroll(p, total_px=px, step_px=step_px, per_step_ms=per_step_ms)
        if linger > 0:
            p.wait_for_timeout(int(linger * 1000))


def capture_product_video(out_webm: Path) -> list[tuple[float, float]]:
    """Record the full product flow with native Playwright video.

    Returns a list of (start_s, end_s) pairs that mark the interesting
    segments of the recording — the parts where something is visibly
    happening. The long waits for strategy/plan API calls get spliced out
    later so the final demo stays tight.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": W, "height": H},
            device_scale_factor=2,
            is_mobile=True, has_touch=True,
            user_agent=("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                        "Mobile/15E148 Safari/604.1"),
            record_video_dir=str(ASSET_DIR),
            record_video_size={"width": W, "height": H},
        )
        p = ctx.new_page()

        # Track (start, end) segments of the video we want to keep.
        t0 = time.monotonic()
        segments: list[tuple[float, float]] = []

        def mark_start() -> float:
            return time.monotonic() - t0

        def mark_end(start: float) -> None:
            segments.append((start, time.monotonic() - t0))

        # ── Step 1: landing ────────────────────────────────────────
        print("  step 1: landing")
        p.goto(BASE_URL, wait_until="networkidle")
        # Dismiss SEBI modal (shows on first visit)
        try:
            p.wait_for_selector("text=I understand", timeout=5_000)
            p.click("text=I understand")
        except Exception:
            pass
        p.wait_for_selector("text=Choose your plan", timeout=10_000)
        seg_start = mark_start()
        p.wait_for_timeout(1_800)
        p.click("text=Start free plan")
        mark_end(seg_start)

        # ── Step 2: profile — scroll through, then fill + submit ───
        print("  step 2: profile")
        p.wait_for_selector("text=Your investor profile", timeout=10_000)
        seg_start = mark_start()
        p.wait_for_timeout(1_000)
        # Select Mid career archetype so the form is pre-filled
        p.locator("button", has_text="Mid career").first.scroll_into_view_if_needed()
        p.wait_for_timeout(600)
        p.locator("button", has_text="Mid career").first.click()
        p.wait_for_timeout(600)

        # Fill the required name field
        p.locator("input[placeholder*='Ravi']").first.fill("Ananya Shetty")
        p.wait_for_timeout(400)

        # Scroll through the profile sections so viewer sees what was pre-filled
        p.evaluate("window.scrollTo(0, 0)")
        p.wait_for_timeout(500)
        _slow_scroll(p, total_px=1200, step_px=30, per_step_ms=35)
        p.wait_for_timeout(800)

        # Scroll to the submit button, click
        p.locator("button", has_text="Build my plan").first.scroll_into_view_if_needed()
        p.wait_for_timeout(600)
        p.click("text=Build my plan")
        mark_end(seg_start)

        # ── Step 3: strategy — scroll through it ────────────────────
        print("  step 3: strategy (may be slow — Together cold start)")
        p.wait_for_url("**/step/3", timeout=15_000)
        # Strategy API can take 30-120s on cold path — don't record that.
        p.wait_for_selector("button:has-text('Generate my plan')", timeout=180_000)
        seg_start = mark_start()
        p.evaluate("window.scrollTo(0, 0)")
        p.wait_for_timeout(1_800)
        # Pan through asset allocation → equity approach → themes → open Qs
        # with a pause on each so viewers can read the content.
        _scroll_with_lingers(p, chunks=[
            (500, 2.0),   # asset allocation
            (500, 2.0),   # equity approach + key themes
            (500, 1.8),   # open questions / "Anything else to adjust?"
        ])
        p.locator("button", has_text="Generate my plan").first.scroll_into_view_if_needed()
        p.wait_for_timeout(900)
        p.click("button:has-text('Generate my plan')")
        mark_end(seg_start)

        # ── Step 4: plan — dismiss reveal modal, scroll through plan ───
        print("  step 4: plan (may be slow)")
        p.wait_for_url("**/step/4", timeout=240_000)
        # Plan generation is slow — only start marking when the reveal modal
        # appears (means the plan is ready).
        p.wait_for_selector("text=I understand — show my plan", timeout=240_000)
        seg_start = mark_start()
        p.wait_for_timeout(1_400)   # let viewer see the modal
        p.click("text=I understand — show my plan")
        p.wait_for_timeout(1_500)   # confetti / blur fade

        # Scroll from top through the full plan with a pause on every major
        # section: allocations → setup → checkpoints → rebalancing →
        # projections → rationale → risks.
        p.evaluate("window.scrollTo(0, 0)")
        p.wait_for_timeout(1_800)   # read allocations
        _scroll_with_lingers(p, chunks=[
            (500, 2.2),   # setup phase
            (500, 2.2),   # review checkpoints
            (500, 2.2),   # rebalancing guidelines
            (500, 2.2),   # projected returns
            (500, 2.2),   # rationale
            (500, 2.5),   # risks
        ])
        mark_end(seg_start)

        ctx.close()
        browser.close()

    # Playwright writes video as <random>.webm in record_video_dir.
    webms = sorted(ASSET_DIR.glob("*.webm"), key=lambda f: f.stat().st_mtime)
    if not webms:
        raise RuntimeError("Playwright did not produce a video")
    webms[-1].rename(out_webm)
    for w in webms[:-1]:
        w.unlink(missing_ok=True)

    print(f"  segments ({len(segments)}): "
          + ", ".join(f"[{s:.1f}-{e:.1f}]" for s, e in segments))
    return segments


# ── Encoding ───────────────────────────────────────────────────────────────────

def encode_mp4_from_segments(src_webm: Path, segments: list[tuple[float, float]],
                              out_mp4: Path, music: Path | None = None,
                              fade_out: float = 0.8) -> None:
    """Cut the source webm into the given segments, concat, transcode to MP4.

    Each segment is one user-visible flow step; the long API waits between
    them are dropped. Result is re-encoded to H.264 baseline / yuv420p.
    """
    # Build a filter_complex that selects + trims + concats each segment.
    vparts = []
    aparts = []
    for i, (s, e) in enumerate(segments):
        vparts.append(
            f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS,"
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H},format=yuv420p[v{i}]"
        )
        aparts.append(
            f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]"
            if music is None else ""  # we'll mux music separately
        )
    vconcat_inputs = "".join(f"[v{i}]" for i in range(len(segments)))
    filter_complex = ";".join(vparts) + f";{vconcat_inputs}concat=n={len(segments)}:v=1:a=0[vout]"

    total = sum(e - s for s, e in segments)

    cmd = ["ffmpeg", "-y", "-i", str(src_webm)]
    if music is not None:
        cmd += ["-i", str(music)]

    # Add music mix to filter
    if music is not None:
        filter_complex += (
            f";[1:a]volume=0.5,afade=t=out:st={max(0.1, total - fade_out):.2f}:"
            f"d={fade_out},atrim=duration={total:.3f}[aout]"
        )
        map_audio = ["-map", "[aout]"]
    else:
        map_audio = ["-an"]

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[vout]", *map_audio,
        "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
        "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
    ]
    if music is not None:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-ar", "44100"]
    cmd += ["-movflags", "+faststart", str(out_mp4)]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2500:])
        raise RuntimeError("ffmpeg segment assembly failed")


def concat_mp4s(inputs: list[Path], out: Path) -> None:
    lst = ASSET_DIR / f"concat_{out.stem}.txt"
    with open(lst, "w") as f:
        for i in inputs:
            f.write(f"file '{i.resolve()}'\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
           "-c", "copy", "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        # Fall back to re-encode if codec copy fails (mismatched params)
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
               "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                      f"pad={W}:{H},format=yuv420p,fps={FPS}",
               "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
               "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
               "-movflags", "+faststart", str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stderr[-2000:])
            raise RuntimeError("ffmpeg concat failed")


def slice_mp4(src: Path, start: float, duration: float, out: Path) -> None:
    """Cut a sub-clip; re-encoded so concat with other encoded clips works."""
    cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(src),
           "-t", f"{duration:.3f}",
           "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                  f"pad={W}:{H},format=yuv420p,fps={FPS}",
           "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
           "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
           "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        raise RuntimeError("ffmpeg slice failed")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=== Subprime Demo Production ===\n")

    print("[1/5] music tracks")
    happy = ASSET_DIR / "music_happy.wav"
    sinister = ASSET_DIR / "music_sinister.wav"
    make_happy_music(60, happy)
    make_sinister_music(20, sinister)

    print("[2/5] intro + stat cards")
    intro_cards: list[Path] = []
    for i, c in enumerate(INTRO_CARDS):
        p = ASSET_DIR / f"intro_{i}.png"
        make_stat_card(c, p, label="SUBPRIME · INTRO")
        intro_cards.append(p)
    stat_cards: list[Path] = []
    for i, c in enumerate(STAT_CARDS):
        p = ASSET_DIR / f"stat_{i}.png"
        make_stat_card(c, p, label="SUBPRIME · RESULTS")
        stat_cards.append(p)
    cards = intro_cards + stat_cards

    print("[3/5] capture product video")
    raw_webm = ASSET_DIR / "product_raw.webm"
    raw_webm.unlink(missing_ok=True)
    segments = capture_product_video(raw_webm)
    if not segments:
        raise RuntimeError("no segments captured")

    print("[4/5] encode product MP4 (spliced to visible segments)")
    product_out = REPO_ROOT / "product" / "finadvisor-demo.mp4"
    encode_mp4_from_segments(raw_webm, segments, product_out, music=happy)
    print(f"  → {product_out} ({product_out.stat().st_size // 1024}KB)")

    print("[5/5] build research MP4 (cards → product)")
    card_dur = 2.5
    card_xfade = 0.4          # crossfade between cards
    cards_to_product_xfade = 0.6
    n_cards = len(cards)

    # 1. Each card as a silent still-MP4 (video-only, no audio track).
    card_clips: list[Path] = []
    for i, card_png in enumerate(cards):
        clip = ASSET_DIR / f"card_{i}.mp4"
        still_to_mp4(card_png, card_dur, clip)
        card_clips.append(clip)

    # 2. Chain-xfade all card clips into one continuous silent video.
    cards_video = ASSET_DIR / "cards_video.mp4"
    filter_parts = []
    cards_total = card_dur
    prev = "[0:v]"
    for i in range(1, n_cards):
        offset = cards_total - card_xfade
        out_label = f"[x{i}]"
        filter_parts.append(
            f"{prev}[{i}:v]xfade=transition=fade:duration={card_xfade}:"
            f"offset={offset:.3f}{out_label}"
        )
        prev = out_label
        cards_total += card_dur - card_xfade
    inputs = []
    for c in card_clips:
        inputs += ["-i", str(c)]
    cmd = ["ffmpeg", "-y", *inputs,
           "-filter_complex", ";".join(filter_parts),
           "-map", prev, "-c:v", "libx264", "-profile:v", "baseline",
           "-level", "3.1", "-preset", "slow", "-crf", "20",
           "-pix_fmt", "yuv420p", "-r", str(FPS),
           "-an", "-movflags", "+faststart", str(cards_video)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        raise RuntimeError("card xfade assembly failed")

    # 3. Slice the plan-reveal portion of the product video. Longer this time
    # since the user asked for more product time in the research video.
    product_slice = ASSET_DIR / "product_slice.mp4"
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(product_out)],
        check=True, capture_output=True, text=True,
    )
    product_dur = float(probe.stdout.strip())
    plan_slice_duration = min(30.0, product_dur - 17.0)
    slice_mp4(product_out, start=max(0.0, product_dur - plan_slice_duration),
              duration=plan_slice_duration, out=product_slice)

    # 4. Continuous sinister-to-happy audio track across the whole research
    # video (no hard cuts at card boundaries).
    total_research_dur = cards_total + plan_slice_duration - cards_to_product_xfade
    sr = 44100
    sinister_long = ASSET_DIR / "music_sinister_long.wav"
    make_sinister_music(cards_total + 0.5, sinister_long)
    happy_long = ASSET_DIR / "music_happy_long.wav"
    make_happy_music(plan_slice_duration + 1.0, happy_long)
    music_mix = ASSET_DIR / "music_mix.wav"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(sinister_long), "-i", str(happy_long),
        "-filter_complex",
        # Sinister plays full length of cards + xfade; happy starts under the
        # handoff, running through the rest. acrossfade stitches them smooth.
        f"[0:a]volume=0.55[s];"
        f"[1:a]volume=0.55[h];"
        f"[s][h]acrossfade=d={cards_to_product_xfade}:c1=tri:c2=tri[m];"
        f"[m]afade=t=in:d=0.6,afade=t=out:st={total_research_dur - 0.8:.3f}:d=0.8[out]",
        "-map", "[out]", "-t", f"{total_research_dur:.3f}",
        str(music_mix),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        raise RuntimeError("audio crossfade failed")

    # 5. xfade the cards video and product video, mux the continuous audio.
    research_out = REPO_ROOT / "research" / "finadvisor-demo.mp4"
    # Video xfade offset = cards_total - cards_to_product_xfade (so product
    # starts appearing during the handoff)
    offset = cards_total - cards_to_product_xfade
    cmd = [
        "ffmpeg", "-y",
        "-i", str(cards_video), "-i", str(product_slice), "-i", str(music_mix),
        "-filter_complex",
        f"[0:v][1:v]xfade=transition=fade:duration={cards_to_product_xfade}:"
        f"offset={offset:.3f}[v]",
        "-map", "[v]", "-map", "2:a",
        "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
        "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-t", f"{total_research_dur:.3f}",
        "-movflags", "+faststart",
        str(research_out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        raise RuntimeError("research assembly failed")
    print(f"  → {research_out} ({research_out.stat().st_size // 1024}KB)")

    print("\n" + "=" * 56)
    print(f"  product  → {product_out}")
    print(f"  research → {research_out}")
    print("=" * 56)


if __name__ == "__main__":
    main()
