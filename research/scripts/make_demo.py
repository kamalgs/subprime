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

BASE_URL = os.environ.get("SUBPRIME_DEMO_URL", "https://finadvisor.gkamal.online")
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
     "sub": "Same persona, same question.\nInject a Lynch (active) or Bogle (passive)\nphilosophy into the hidden system prompt.\nMeasure how the plan shifts."},
    {"headline": "Two scores",
     "sub": "APS — Active-Passive Score\n0 = active, 1 = index / passive\n\nPQS — Plan Quality Score\ngoal fit, diversification, risk, taxes"},
]

STAT_CARDS = [
    {"headline": "5 models\n1,974 plans",
     "sub": "Claude · DeepSeek · GLM · Haiku · Llama"},
    {"headline": "APS shift\n+0.07 → +0.24",
     "sub": "Hidden prompt moves the advice.\nPQS (quality) barely budges."},
    {"headline": "Cohen's d = 1.18",
     "sub": "Large effect size on APS.\nPQS spread < 0.03 across models."},
    {"headline": "Dose-response\n0.168 → 0.783",
     "sub": "APS scales monotonically with\nprompt intensity.\nThe prompt is the bias."},
]

DEMO_CARDS = [
    {"headline": "The demo",
     "sub": "Here's what one of those plans\nactually looks like to a user."},
]


# ── Music ──────────────────────────────────────────────────────────────────────

def _write_wav(path: Path, samples: np.ndarray, sr: int = 44100) -> None:
    pcm = (samples * 32767).astype(np.int16)
    with wave.open(str(path), "w") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
        f.writeframes(pcm.tobytes())


def make_happy_music(duration: float, path: Path, sr: int = 44100,
                      crescendo_at: float | None = None) -> None:
    """Layered build that gains tempo and density toward a peak.

    The arrangement enters in five stages — pad, bass, arp, chord stabs, kick
    — each layer joining a few seconds after the previous. Tempo ramps from
    ~80 BPM at the start to ~120 BPM at the peak. If `crescendo_at` is set,
    the peak lands at that timestamp (otherwise at 70% of the duration). A
    short tail after the peak fades the kit out and leaves the pad ringing.

    All synthesis is sine-based so it stays clean under speech/UI sound and
    doesn't fight the visuals. Output is mono 16-bit PCM.
    """
    n = int(sr * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    peak = crescendo_at if crescendo_at is not None else duration * 0.7
    peak = float(np.clip(peak, 4.0, duration - 1.0))

    # Smooth gain ramps. `s_curve` is a soft 0→1 over [a, b]; `bell` peaks at p.
    def s_curve(a: float, b: float) -> np.ndarray:
        x = np.clip((t - a) / max(1e-3, b - a), 0.0, 1.0)
        return 0.5 - 0.5 * np.cos(np.pi * x)

    def bell(centre: float, halfwidth: float) -> np.ndarray:
        x = (t - centre) / halfwidth
        return np.exp(-x * x)

    # ── Layer 1: low pad (always on, ducks slightly under the peak) ────────
    # A_minor chord (A2, C4, E4) — gentle melancholy bed.
    pad = (np.sin(2 * np.pi * 110.00 * t) * 0.50
           + np.sin(2 * np.pi * 261.63 * t) * 0.20
           + np.sin(2 * np.pi * 329.63 * t) * 0.15)
    pad *= 0.9 + 0.1 * np.sin(2 * np.pi * 0.15 * t)  # very slow swell
    pad_gain = 0.55 + 0.10 * s_curve(0, peak)
    signal = pad * pad_gain

    # ── Layer 2: bass walk (joins ~15% in) ─────────────────────────────────
    # I → V → vi → IV walk in A minor. Half-note pulses for the first half,
    # quarter notes near the peak. Bass starts subdued, swells with the build.
    bass_in = duration * 0.18
    bass_gain = 0.4 * s_curve(bass_in, bass_in + 6.0)
    bass_notes = [110.00, 164.81, 130.81, 146.83]  # A2, E3, C3, D3
    # Tempo ramp: 0.5 Hz at start → 2 Hz at peak
    tempo = 0.5 + (2.0 - 0.5) * np.clip(t / peak, 0.0, 1.0)
    phase = np.cumsum(tempo) / sr  # integrated tempo gives note-onset clock
    bass_signal = np.zeros(n)
    last_step = -1
    for i in range(n):
        step = int(phase[i] * 2) % len(bass_notes)
        if step != last_step:
            last_step = step
            bass_signal[i] = 1.0  # mark onset
    # Build bass tone with per-onset envelope
    bass_wave = np.zeros(n)
    bass_idx = 0
    onsets = np.where(bass_signal > 0)[0]
    for k in range(len(onsets)):
        o = onsets[k]
        end = onsets[k + 1] if k + 1 < len(onsets) else min(o + sr, n)
        note = bass_notes[bass_idx % len(bass_notes)]
        bass_idx += 1
        seg = end - o
        env = np.exp(-np.linspace(0, 3, seg))
        bass_wave[o:end] = np.sin(2 * np.pi * note * t[o:end]) * env
    signal += bass_wave * bass_gain

    # ── Layer 3: arp (joins ~35% in, ramps with tempo) ─────────────────────
    arp_in = duration * 0.35
    arp_gain = 0.30 * s_curve(arp_in, arp_in + 5.0)
    arp_notes = [440.0, 523.25, 659.25, 523.25]  # A4 C5 E5 C5
    arp_phase = np.cumsum(tempo * 4) / sr  # 4× the bass tempo
    arp_wave = np.zeros(n)
    last_arp = -1
    for i in range(n):
        step = int(arp_phase[i]) % len(arp_notes)
        if step != last_arp:
            last_arp = step
            note = arp_notes[step]
            seg = min(int(sr * 0.18), n - i)
            env = np.exp(-np.linspace(0, 5, seg))
            arp_wave[i:i + seg] += np.sin(2 * np.pi * note * t[i:i + seg]) * env
    signal += arp_wave * arp_gain

    # ── Layer 4: chord stabs (joins ~55% in, peaks at crescendo) ───────────
    stab_in = duration * 0.55
    stab_gain = 0.45 * bell(peak, peak - stab_in + 1.0) * s_curve(stab_in, peak)
    stab_freqs = [220.0, 261.63, 329.63, 392.0]  # A3 C4 E4 G4
    stab_wave = np.zeros(n)
    stab_period = sr  # one stab per second around the build
    for o in range(int(stab_in * sr), n - sr // 4, stab_period):
        seg = min(sr // 2, n - o)
        env = np.exp(-np.linspace(0, 6, seg))
        for f in stab_freqs:
            stab_wave[o:o + seg] += np.sin(2 * np.pi * f * t[o:o + seg]) * env / len(stab_freqs)
    signal += stab_wave * stab_gain

    # ── Layer 5: kick (joins last, peaks at crescendo, drops out after) ────
    kick_in = duration * 0.65
    kick_gain = 0.55 * bell(peak, 4.0) * s_curve(kick_in, peak)
    kick_wave = np.zeros(n)
    kick_phase = np.cumsum(tempo) / sr  # one kick per bass-quarter
    last_kick = -1
    for i in range(n):
        step = int(kick_phase[i] * 2)
        if step != last_kick:
            last_kick = step
            seg = min(int(sr * 0.18), n - i)
            # Kick = decaying low sine + click
            decay = np.linspace(0, 8, seg)
            kick = np.sin(2 * np.pi * 60 * t[i:i + seg]) * np.exp(-decay)
            kick_wave[i:i + seg] += kick
    signal += kick_wave * kick_gain

    # Soft saturation to glue layers
    signal = np.tanh(signal * 0.9) * 0.95

    # Normalise + envelope
    signal /= max(1.0, np.max(np.abs(signal)) * 1.05)
    fade = int(sr * 0.6)
    signal[:fade] *= np.linspace(0, 1, fade)
    tail = int(sr * 1.5)
    signal[-tail:] *= np.linspace(1, 0, tail)
    _write_wav(path, signal, sr)


def make_sinister_music(duration: float, path: Path, sr: int = 44100) -> None:
    """Subtle, sinister atmospheric pad. No bass groove, no resolution.

    A minor-key pad sits under a slow ~1 Hz amplitude throb. Every ~8s a
    short dissonant cluster fades in and out — the only "event" in the
    track. The intent is unease, not menace; it should sit under speech
    without competing with it.
    """
    n = int(sr * duration)
    t = np.linspace(0, duration, n, endpoint=False)

    # Pad: A minor with a low D underneath. Detuned doublings give breathing.
    def detuned(freq: float, weight: float, detune_hz: float = 0.4) -> np.ndarray:
        return weight * 0.5 * (
            np.sin(2 * np.pi * freq * t)
            + np.sin(2 * np.pi * (freq + detune_hz) * t)
        )

    pad = (detuned(73.42, 0.35)   # D2 (low pedal)
           + detuned(110.00, 0.30)  # A2
           + detuned(164.81, 0.20)  # E3
           + detuned(207.65, 0.12)  # G#3 — leading-tone tension
           + detuned(261.63, 0.10)) # C4

    # Slow throb: ~1 Hz amplitude modulation, gentle (does not modulate to silence)
    throb = 0.78 + 0.22 * np.sin(2 * np.pi * 1.0 * t)
    pad = pad * throb

    # Slow filter-like timbre shift: very low LFO modulating high partials
    sparkle = 0.05 * np.sin(2 * np.pi * 1318.51 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.07 * t))
    pad += sparkle

    # Dissonant clusters every ~8 seconds. Tritone + semitone above pad root.
    cluster_signal = np.zeros(n)
    cluster_period = int(sr * 8.5)
    cluster_dur = int(sr * 2.0)
    for start in range(int(sr * 4), n, cluster_period):
        seg = min(cluster_dur, n - start)
        # F#3 (185 Hz) = tritone above C4 root region; D#4 = semitone clash
        env = np.sin(np.linspace(0, np.pi, seg)) ** 2  # smooth swell + decay
        cluster = (np.sin(2 * np.pi * 185.0 * t[start:start + seg]) * 0.10
                   + np.sin(2 * np.pi * 311.13 * t[start:start + seg]) * 0.06)
        cluster_signal[start:start + seg] += cluster * env

    signal = pad + cluster_signal

    # Soft saturation + normalise
    signal = np.tanh(signal * 0.85)
    signal /= max(1.0, np.max(np.abs(signal)) * 1.1)

    fade = int(sr * 1.2)
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
        font_big = ImageFont.truetype(FONT_BOLD, 52)
        font_label = ImageFont.truetype(FONT_REG, 14)
    except Exception:
        font_big = ImageFont.load_default(); font_label = font_big

    draw.text((W // 2, H // 2 - 170), label,
              font=font_label, fill=(200, 80, 80), anchor="mm")
    draw.line([(W // 2 - 100, H // 2 - 138), (W // 2 + 100, H // 2 - 138)],
              fill=(80, 80, 100), width=1)
    # Headline: larger + brighter for legibility on small screens.
    draw.text((W // 2, H // 2 - 38), card["headline"],
              font=font_big, fill=(245, 245, 255), anchor="mm", align="center",
              spacing=8)

    sub = card["sub"]
    size = 24
    while size > 13:
        f = ImageFont.truetype(FONT_REG, size)
        widest = max(draw.textlength(line, font=f) for line in sub.split("\n"))
        if widest <= W - 56:
            break
        size -= 1
    draw.text((W // 2, H // 2 + 110), sub,
              font=ImageFont.truetype(FONT_REG, size),
              fill=(195, 195, 220), anchor="mm", align="center", spacing=6)

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
                         step_px: int = 18, per_step_ms: int = 70) -> None:
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
        # Hide experimental features (document upload, CAS upload) on every page.
        # Targeting is by visible heading text + structural class because the
        # production build minifies component names.
        HIDE_EXPERIMENTAL_CSS = """
            /* Hide DocumentsUpload / CASUpload cards by their heading text */
            .card:has(> div > .section-title:is(:where(*))) {}
        """
        # Stronger approach: a runtime hook that scans for the known headings
        # and hides their nearest .card ancestor on every render.
        HIDE_EXPERIMENTAL_JS = """
            (() => {
              const HEADINGS = [
                'Supporting documents',
                'Documents processed',
                'Your current holdings',
                'Upload CAS',
              ];
              const hide = () => {
                document.querySelectorAll('h2, h3').forEach((h) => {
                  if (HEADINGS.some((s) => h.textContent && h.textContent.includes(s))) {
                    let card = h.closest('.card') || h.closest('section') || h.parentElement;
                    if (card) card.style.display = 'none';
                  }
                });
              };
              hide();
              const obs = new MutationObserver(hide);
              obs.observe(document.body, { childList: true, subtree: true });
            })();
        """

        def install_hide_hook() -> None:
            try:
                p.add_init_script(HIDE_EXPERIMENTAL_JS)
            except Exception:
                pass

        install_hide_hook()
        p.goto(BASE_URL, wait_until="networkidle")
        # Run the hook again post-mount in case the script executed too early.
        try:
            p.evaluate(HIDE_EXPERIMENTAL_JS)
        except Exception:
            pass
        # Dismiss SEBI modal (shows on first visit)
        try:
            p.wait_for_selector("text=I understand", timeout=5_000)
            p.click("text=I understand")
        except Exception:
            pass
        p.wait_for_selector("text=Choose your plan", timeout=10_000)
        seg_start = mark_start()
        p.wait_for_timeout(2_400)   # slower opener — lets music breathe in
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

        # Save the profile first — the form has a two-stage submit:
        # Save profile → DocumentsUpload appears (we hide it) → Build my plan.
        p.locator("button", has_text="Save profile").first.scroll_into_view_if_needed()
        p.wait_for_timeout(600)
        p.click("text=Save profile")
        # Wait for the saved-state to render the build button. If save 422s
        # (validation error) the saved flag never flips and Build never appears
        # — capture diagnostics in that case.
        try:
            p.wait_for_selector("button:has-text('Build my plan')", timeout=15_000)
        except Exception:
            shot = ASSET_DIR / "step2_save_timeout.png"
            try:
                p.screenshot(path=str(shot), full_page=True)
                body_text = p.evaluate("() => document.body.innerText")[:1500]
                print(f"  step2 save timeout — url={p.url}")
                print(f"  step2 page text:\n{body_text}")
                print(f"  screenshot: {shot}")
            except Exception:
                pass
            raise
        # Re-run the hide hook now that DocumentsUpload has mounted.
        try:
            p.evaluate(HIDE_EXPERIMENTAL_JS)
        except Exception:
            pass
        p.locator("button", has_text="Build my plan").first.scroll_into_view_if_needed()
        p.wait_for_timeout(600)
        p.click("text=Build my plan")
        mark_end(seg_start)

        # ── Step 3: strategy — scroll through it ────────────────────
        print("  step 3: strategy")
        p.wait_for_url("**/step/3", timeout=15_000)
        # Strategy returns in ~5-10s on prod (measured). On error, dump
        # page state for diagnosis instead of timing out silently.
        try:
            p.wait_for_selector("button:has-text('Generate my plan')", timeout=120_000)
        except Exception:
            shot = ASSET_DIR / "step3_timeout.png"
            try:
                p.screenshot(path=str(shot), full_page=True)
                body_text = p.evaluate("() => document.body.innerText")[:1500]
                url = p.url
                print(f"  step3 timeout — url={url}")
                print(f"  step3 page text (first 1500 chars):\n{body_text}")
                print(f"  screenshot saved: {shot}")
            except Exception:
                pass
            raise
        seg_start = mark_start()
        p.evaluate("window.scrollTo(0, 0)")
        p.wait_for_timeout(1_800)
        # Pan through asset allocation → equity approach → themes → open Qs
        # with a pause on each so viewers can read the content.
        _scroll_with_lingers(p, chunks=[
            (500, 2.6),   # asset allocation
            (500, 2.6),   # equity approach + key themes
            (500, 2.4),   # open questions / "Anything else to adjust?"
        ])
        p.locator("button", has_text="Generate my plan").first.scroll_into_view_if_needed()
        p.wait_for_timeout(900)
        p.click("button:has-text('Generate my plan')")
        mark_end(seg_start)

        # ── Step 4: plan — dismiss reveal modal, scroll through plan ───
        print("  step 4: plan (may be slow)")
        p.wait_for_url("**/step/4", timeout=240_000)
        # Plan generation is slow — only start marking when the reveal modal
        # appears (means the plan is ready). Production sometimes takes >4 min
        # on first call due to OpenRouter cold starts; allow up to 8 min.
        try:
            p.wait_for_selector("text=I understand — show my plan", timeout=480_000)
        except Exception as e:
            shot = ASSET_DIR / "step4_timeout.png"
            try:
                p.screenshot(path=str(shot), full_page=True)
                print(f"  step4 timeout — screenshot saved: {shot}")
            except Exception:
                pass
            raise
        seg_start = mark_start()
        p.wait_for_timeout(2_400)   # longer linger on the reveal modal so the
                                    # crescendo lands on the click
        p.click("text=I understand — show my plan")
        p.wait_for_timeout(1_800)   # confetti / blur fade

        # Scroll from top through the full plan with a pause on every major
        # section: allocations → setup → checkpoints → rebalancing →
        # projections → rationale → risks.
        p.evaluate("window.scrollTo(0, 0)")
        p.wait_for_timeout(2_400)   # read allocations
        _scroll_with_lingers(p, chunks=[
            (500, 2.8),   # setup phase
            (500, 2.8),   # review checkpoints
            (500, 2.8),   # rebalancing guidelines
            (500, 2.8),   # projected returns
            (500, 3.0),   # rationale
            (500, 3.2),   # risks
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
                              fade_out: float = 1.2,
                              fade_in: float = 0.6) -> None:
    """Cut the source webm into the given segments, concat, transcode to MP4.

    Each segment is one user-visible flow step; the long API waits between
    them are dropped. Result is re-encoded to H.264 baseline / yuv420p with
    a fade-in from black at the start and fade-out at the end so the video
    doesn't slam in and out.
    """
    vparts = []
    for i, (s, e) in enumerate(segments):
        vparts.append(
            f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS,"
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H},format=yuv420p[v{i}]"
        )
    vconcat_inputs = "".join(f"[v{i}]" for i in range(len(segments)))
    total = sum(e - s for s, e in segments)
    fout_start = max(0.1, total - fade_out)
    filter_complex = ";".join(vparts) + (
        f";{vconcat_inputs}concat=n={len(segments)}:v=1:a=0[vc]"
        f";[vc]fade=t=in:st=0:d={fade_in},"
        f"fade=t=out:st={fout_start:.3f}:d={fade_out}[vout]"
    )

    cmd = ["ffmpeg", "-y", "-i", str(src_webm)]
    if music is not None:
        cmd += ["-i", str(music)]

    if music is not None:
        # Light volume on the music bed; afade-in/out align with video fades.
        filter_complex += (
            f";[1:a]volume=0.55,"
            f"afade=t=in:st=0:d={fade_in},"
            f"afade=t=out:st={fout_start:.2f}:d={fade_out},"
            f"atrim=duration={total:.3f}[aout]"
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
    # Generate placeholders; the actual product score is regenerated below
    # once we know the recording length and where the plan-reveal happens.
    make_happy_music(60, happy)
    make_sinister_music(60, sinister)

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
    demo_cards: list[Path] = []
    for i, c in enumerate(DEMO_CARDS):
        p = ASSET_DIR / f"demo_{i}.png"
        make_stat_card(c, p, label="SUBPRIME · DEMO")
        demo_cards.append(p)
    cards = intro_cards + stat_cards + demo_cards

    print("[3/5] capture product video")
    raw_webm = ASSET_DIR / "product_raw.webm"
    raw_webm.unlink(missing_ok=True)
    segments = capture_product_video(raw_webm)
    if not segments:
        raise RuntimeError("no segments captured")

    print("[4/5] encode product MP4 (spliced to visible segments)")
    product_out = REPO_ROOT / "product" / "finadvisor-demo.mp4"
    # Crescendo lands on the start of the final segment (plan reveal).
    final_total = sum(e - s for s, e in segments)
    pre_plan = sum(e - s for s, e in segments[:-1])
    crescendo_at = pre_plan + 2.0  # 2s into the plan reveal segment (post-modal click)
    make_happy_music(final_total + 0.5, happy, crescendo_at=crescendo_at)
    print(f"  product score: duration={final_total:.1f}s, crescendo at {crescendo_at:.1f}s")
    encode_mp4_from_segments(raw_webm, segments, product_out, music=happy)
    print(f"  → {product_out} ({product_out.stat().st_size // 1024}KB)")

    print("[5/5] build research MP4 (cards → product)")
    card_dur = 5.5            # slower per-card linger for legibility
    card_xfade = 1.0          # slower crossfade
    cards_to_product_xfade = 1.2
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

    # 4. Single sinister track across the whole research video. The arc is
    # subtle and unresolved — no shift to a major key under the product
    # reveal. The pad ducks slightly under the product slice so the (silent)
    # UI footage doesn't feel buried.
    total_research_dur = cards_total + plan_slice_duration - cards_to_product_xfade
    sinister_long = ASSET_DIR / "music_sinister_long.wav"
    make_sinister_music(total_research_dur + 1.0, sinister_long)
    music_mix = ASSET_DIR / "music_mix.wav"
    duck_start = cards_total - cards_to_product_xfade
    cmd = [
        "ffmpeg", "-y",
        "-i", str(sinister_long),
        "-filter_complex",
        # Volume envelope: 0.55 over cards, ducks to 0.40 during product
        # slice. afade-in/out tops and tails the track cleanly.
        f"[0:a]volume='if(lt(t,{duck_start:.2f}),0.55,"
        f"if(lt(t,{duck_start + 1.5:.2f}),"
        f"0.55+(0.40-0.55)*((t-{duck_start:.2f})/1.5),"
        f"0.40))':eval=frame,"
        f"afade=t=in:d=1.0,"
        f"afade=t=out:st={total_research_dur - 1.5:.3f}:d=1.5[out]",
        "-map", "[out]", "-t", f"{total_research_dur:.3f}",
        str(music_mix),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        raise RuntimeError("audio mix failed")

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
