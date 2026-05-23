#!/usr/bin/env python3
"""
Build 3 Meta-ready MP4 ads from PNG masters in ADS/ folder.
Outputs: 5s, 1080x1080, H.264, yuv420p, 30fps, silent AAC audio, <10MB each.
"""

import os
import sys
import math
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

ADS_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = '/tmp/ecd_ads_build'
FPS = 30
DURATION = 5.0
TOTAL_FRAMES = int(FPS * DURATION)  # 150

FFMPEG = '/opt/homebrew/bin/ffmpeg'
FFPROBE = '/opt/homebrew/bin/ffprobe'

# Fonts
HN = '/System/Library/Fonts/HelveticaNeue.ttc'
# index 0 = Regular, 1 = Bold, 10 = Medium, 7 = Light, 5 = UltraLight
MONO = '/System/Library/Fonts/SFNSMono.ttf'


def F(size, weight='regular'):
    idx = {'regular': 0, 'bold': 1, 'medium': 10, 'light': 7}[weight]
    return ImageFont.truetype(HN, size, index=idx)


def F_mono(size):
    return ImageFont.truetype(MONO, size)


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def ease_out_back(t, s=1.70158):
    return 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2


def lerp(a, b, t):
    return a + (b - a) * t


def encode_mp4(frames_dir, out_path):
    """Encode frame_%04d.png in frames_dir to silent-audio MP4."""
    if os.path.exists(out_path):
        os.remove(out_path)
    cmd = [
        FFMPEG, '-y', '-loglevel', 'error',
        '-framerate', str(FPS),
        '-i', os.path.join(frames_dir, 'frame_%04d.png'),
        '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000',
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-r', str(FPS),
        '-t', str(DURATION),
        '-c:a', 'aac',
        '-b:a', '128k',
        '-shortest',
        '-movflags', '+faststart',
        '-preset', 'medium',
        '-crf', '22',
        out_path
    ]
    subprocess.run(cmd, check=True)


# ============================================================
# AD 1 — RECEIPT WITH CANCEL STAMP
# ============================================================

def extract_stamp_from_ad1():
    """Pull the red CANCEL THIS stamp out of the original PNG as a transparent overlay.
    Returns (stamp_rgba, center_x, center_y) where center is in the original 1080x1080 frame."""
    src = Image.open(os.path.join(ADS_DIR, 'ecd_ad1_receipt.png')).convert('RGB')
    W, H = src.size
    stamp = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    spx = stamp.load()
    spx_src = src.load()

    minx, miny, maxx, maxy = W, H, 0, 0
    cnt = 0
    sumx = sumy = 0

    for y in range(H):
        if y < 200 or y > 760:
            # Exclude the orange GHL header and anything outside the stamp's y-range
            continue
        for x in range(W):
            r, g, b = spx_src[x, y]
            # Detect red stamp pixels — tight enough to exclude the orange GHL box (g=107)
            if r > 130 and g < 95 and b < 95 and r - max(g, b) > 40 and abs(int(g) - int(b)) < 25:
                # Reconstruct the stamp's red color
                spx[x, y] = (r, g, b, 255)
                if x < minx: minx = x
                if x > maxx: maxx = x
                if y < miny: miny = y
                if y > maxy: maxy = y
                cnt += 1
                sumx += x
                sumy += y

    cx = sumx / cnt
    cy = sumy / cnt

    # Crop the stamp to its tight bbox with a small padding
    pad = 10
    bbox = (max(0, minx - pad), max(0, miny - pad), min(W, maxx + pad), min(H, maxy + pad))
    stamp_cropped = stamp.crop(bbox)
    # Recompute center within the cropped image
    crop_cx = cx - bbox[0]
    crop_cy = cy - bbox[1]
    # Position to paste so center lands at original (cx, cy)
    return stamp_cropped, bbox[0], bbox[1], cx, cy


def build_clean_receipt():
    """Build a 'no stamp' base by painting white over the stamp area and redrawing line items."""
    src = Image.open(os.path.join(ADS_DIR, 'ecd_ad1_receipt.png')).convert('RGB').copy()
    draw = ImageDraw.Draw(src)

    # Paint white over the entire stamp area (covers line items + divider + total row)
    # Receipt card is from ~x=70 to x=1015. Stamp area roughly y=375 to y=720.
    draw.rectangle([(75, 375), (1015, 720)], fill=(255, 255, 255))

    # Redraw 4 line items + divider + TOTAL row + Annual line
    body_font = F(30, 'regular')
    bold_font = F(32, 'bold')

    items = [
        ('GoHighLevel Pro — Monthly subscription', '$297.00'),
        ('Twilio messaging add-on',                '$45.00'),
        ('Workflow automation seats (2)',          '$58.00'),
        ('Funnel builder upgrade',                 '$38.00'),
    ]

    y = 395
    text_color = (35, 35, 35)
    for label, amount in items:
        draw.text((110, y), label, font=body_font, fill=text_color)
        # Right-align amount
        amt_bbox = draw.textbbox((0, 0), amount, font=body_font)
        amt_w = amt_bbox[2] - amt_bbox[0]
        draw.text((990 - amt_w, y), amount, font=body_font, fill=text_color)
        y += 56

    # Divider
    draw.line([(110, 626), (990, 626)], fill=(220, 218, 212), width=1)

    # TOTAL THIS MONTH row
    total_label = 'TOTAL THIS MONTH'
    total_amount = '$438.00'
    draw.text((110, 660), total_label, font=bold_font, fill=(20, 20, 20))
    amt_bbox = draw.textbbox((0, 0), total_amount, font=bold_font)
    amt_w = amt_bbox[2] - amt_bbox[0]
    draw.text((990 - amt_w, 660), total_amount, font=bold_font, fill=(20, 20, 20))

    # Annual line
    annual_font = F(22, 'regular')
    draw.text((110, 708), 'Annual: $5,256.00 — and you own none of it.',
              font=annual_font, fill=(140, 140, 140))

    return src


def build_ad1():
    print('\n=== AD 1: Receipt ===')
    frames_dir = os.path.join(TMP_DIR, 'ad1')
    if os.path.exists(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir, exist_ok=True)

    print('  extracting stamp...')
    stamp_overlay, stamp_x, stamp_y, stamp_cx, stamp_cy = extract_stamp_from_ad1()
    # stamp_overlay is a tight crop. stamp_x/stamp_y is where to paste to align with original.

    print('  building clean base...')
    clean_base = build_clean_receipt()
    stamped_orig = Image.open(os.path.join(ADS_DIR, 'ecd_ad1_receipt.png')).convert('RGB')

    sw, sh = stamp_overlay.size
    stamp_local_cx = stamp_cx - stamp_x
    stamp_local_cy = stamp_cy - stamp_y

    cta_y1, cta_y2 = 920, 1020

    print(f'  rendering {TOTAL_FRAMES} frames...')
    for i in range(TOTAL_FRAMES):
        t = i / FPS

        if t < 1.5:
            # Clean — no stamp
            frame = clean_base.copy()
        elif t < 2.0:
            # Stamp slamming in
            p = (t - 1.5) / 0.5  # 0 to 1
            ease = ease_out_cubic(p)
            scale = lerp(1.3, 1.0, ease)
            alpha = lerp(0.3, 1.0, ease)

            # Shake near the end (last 20% of the slam)
            shake_x = shake_y = 0
            if p > 0.8:
                sp = (p - 0.8) / 0.2  # 0 to 1
                damp = 1 - sp
                shake_x = int(math.sin(sp * 25) * 6 * damp)
                shake_y = int(math.cos(sp * 28) * 3 * damp)

            # Scale stamp
            new_w = max(1, int(sw * scale))
            new_h = max(1, int(sh * scale))
            scaled = stamp_overlay.resize((new_w, new_h), Image.LANCZOS)
            # Apply alpha
            if alpha < 1.0:
                a = scaled.split()[3].point(lambda px: int(px * alpha))
                scaled.putalpha(a)
            # Position so the scaled stamp's center aligns with original center (+ shake)
            px = int(stamp_cx - new_w * (stamp_local_cx / sw)) + shake_x
            py = int(stamp_cy - new_h * (stamp_local_cy / sh)) + shake_y

            frame = clean_base.copy()
            frame_rgba = frame.convert('RGBA')
            frame_rgba.alpha_composite(scaled, (px, py))
            frame = frame_rgba.convert('RGB')
        elif t < 4.0:
            # Hold — full stamped original
            frame = stamped_orig.copy()
        else:
            # CTA pulse: scale 1.0 -> 1.02 -> 1.0 across the second
            frame = stamped_orig.copy()
            pt = (t - 4.0) / 1.0  # 0 to 1
            # Two soft pulses
            pulse = 1.0 + 0.02 * math.sin(pt * math.pi * 2) * math.sin(pt * math.pi)
            # Crop CTA region
            cta_w = 1080
            cta_h = cta_y2 - cta_y1
            cta = frame.crop((0, cta_y1, cta_w, cta_y2))
            # Scale
            new_w = int(cta_w * pulse)
            new_h = int(cta_h * pulse)
            cta_scaled = cta.resize((new_w, new_h), Image.LANCZOS)
            # Paint white over the original CTA area first, then re-paste scaled
            ImageDraw.Draw(frame).rectangle([(0, cta_y1 - 4), (cta_w, cta_y2 + 4)],
                                            fill=(255, 255, 255))
            # Position centered horizontally on the CTA bar's vertical center
            cta_center_y = (cta_y1 + cta_y2) // 2
            px = (cta_w - new_w) // 2
            py = cta_center_y - new_h // 2
            frame.paste(cta_scaled, (px, py))

        frame.save(os.path.join(frames_dir, f'frame_{i:04d}.png'),
                   optimize=False, compress_level=1)

    out = os.path.join(ADS_DIR, 'ecd_ad1_receipt.mp4')
    print(f'  encoding -> {out}')
    encode_mp4(frames_dir, out)
    return out


# ============================================================
# AD 2 — IMESSAGE TEXT THREAD
# ============================================================

def build_ad2():
    print('\n=== AD 2: Text Message ===')
    frames_dir = os.path.join(TMP_DIR, 'ad2')
    if os.path.exists(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir, exist_ok=True)

    src_orig = Image.open(os.path.join(ADS_DIR, 'ecd_ad2_textmessage.png')).convert('RGB')

    # Define bubble bounding boxes (measured from PNG: gray ≈ (44,44,46), blue ≈ (10,132,255))
    bubbles = [
        {'bbox': (40, 270, 525, 400),   'side': 'L', 'enter_t': 0.5},
        {'bbox': (570, 420, 1040, 605), 'side': 'R', 'enter_t': 1.5},
        {'bbox': (40, 625, 525, 720),   'side': 'L', 'enter_t': 2.5},
        {'bbox': (560, 740, 1040, 970), 'side': 'R', 'enter_t': 3.5},
    ]
    # Crop each bubble from the original
    for b in bubbles:
        b['img'] = src_orig.crop(b['bbox']).convert('RGBA')
        b['w'] = b['bbox'][2] - b['bbox'][0]
        b['h'] = b['bbox'][3] - b['bbox'][1]

    # Build "empty thread" base: original PNG with all 4 bubble areas painted black
    empty_base = src_orig.copy()
    draw = ImageDraw.Draw(empty_base)
    for b in bubbles:
        # Generous padding to cover anti-aliased edges
        x1, y1, x2, y2 = b['bbox']
        draw.rectangle([(x1 - 12, y1 - 12), (x2 + 12, y2 + 12)], fill=(0, 0, 0))

    # Typing dots: small gray bubble with three pulsing dots
    def render_typing_bubble(side):
        # Returns RGBA image of a typing-indicator bubble
        bub_w, bub_h = 130, 65
        img = Image.new('RGBA', (bub_w, bub_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # Rounded rect (gray bubble, like incoming style)
        bg = (60, 60, 60, 255) if side == 'L' else (10, 120, 230, 255)
        d.rounded_rectangle([(0, 0), (bub_w, bub_h)], radius=24, fill=bg)
        # Three dots
        for i in range(3):
            cx = 32 + i * 32
            cy = bub_h // 2
            d.ellipse([(cx - 7, cy - 7), (cx + 7, cy + 7)], fill=(180, 180, 180, 255))
        return img

    typing_L = render_typing_bubble('L')
    typing_R = render_typing_bubble('R')

    print(f'  rendering {TOTAL_FRAMES} frames...')
    for i in range(TOTAL_FRAMES):
        t = i / FPS
        frame = empty_base.copy().convert('RGBA')

        for b_idx, b in enumerate(bubbles):
            et = b['enter_t']
            slide_dur = 0.35  # slide-in duration
            typing_dur = 0.30  # typing indicator before the bubble

            # Typing indicator phase: appears 0.3s before enter_t
            typing_start = et - typing_dur
            typing_end = et

            if typing_start <= t < typing_end:
                # Show typing dots at this bubble's start position
                ti = typing_L if b['side'] == 'L' else typing_R
                # Position: aligned with bubble's start
                x1 = b['bbox'][0]
                # Place typing bubble at the top of where the message will go,
                # offset so dots are inline with bubble start
                tx = x1 if b['side'] == 'L' else (b['bbox'][2] - ti.size[0])
                ty = b['bbox'][1] + 8
                # Subtle pulse the typing dots opacity
                pulse = 0.55 + 0.45 * abs(math.sin((t - typing_start) * 8))
                ti_copy = ti.copy()
                a = ti_copy.split()[3].point(lambda p: int(p * pulse))
                ti_copy.putalpha(a)
                frame.alpha_composite(ti_copy, (tx, ty))

            # Bubble slide-in phase
            if t >= et:
                slide_p = min(1.0, (t - et) / slide_dur)
                ease = ease_out_cubic(slide_p)

                if b['side'] == 'L':
                    # Slide up from bottom of its target area
                    y_offset = int((1 - ease) * 80)  # 80px slide up
                    x_offset = 0
                    # Slight fade in
                    alpha = lerp(0.5, 1.0, ease) if slide_p < 1 else 1.0
                else:
                    # Slide in from right
                    x_offset = int((1 - ease) * 200)
                    y_offset = int((1 - ease) * 30)
                    alpha = lerp(0.5, 1.0, ease) if slide_p < 1 else 1.0

                x1, y1, _, _ = b['bbox']
                bx = x1 + x_offset
                by = y1 + y_offset

                img = b['img']
                if alpha < 1.0:
                    img_copy = img.copy()
                    a = img_copy.split()[3].point(lambda p: int(p * alpha))
                    img_copy.putalpha(a)
                    frame.alpha_composite(img_copy, (bx, by))
                else:
                    frame.alpha_composite(img, (bx, by))

        frame.convert('RGB').save(os.path.join(frames_dir, f'frame_{i:04d}.png'),
                                  optimize=False, compress_level=1)

    out = os.path.join(ADS_DIR, 'ecd_ad2_textmessage.mp4')
    print(f'  encoding -> {out}')
    encode_mp4(frames_dir, out)
    return out


# ============================================================
# AD 3 — WHITEBOARD MATH
# ============================================================

def build_ad3():
    print('\n=== AD 3: Whiteboard Math ===')
    frames_dir = os.path.join(TMP_DIR, 'ad3')
    if os.path.exists(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir, exist_ok=True)

    src_orig = Image.open(os.path.join(ADS_DIR, 'ecd_ad3_whiteboard.png')).convert('RGB')

    # Sample the paper background color
    bg_color = src_orig.getpixel((30, 30))  # cream/off-white

    # Bboxes derived from per-color row scans on the source PNG
    elements = [
        # 4 line items appearing 0.3s - 2.0s
        {'bbox': (75, 155, 990, 230),   'start': 0.3,  'reveal_dur': 0.30, 'name': 'L1'},
        {'bbox': (75, 245, 990, 320),   'start': 0.7,  'reveal_dur': 0.30, 'name': 'L2'},
        {'bbox': (75, 335, 990, 400),   'start': 1.1,  'reveal_dur': 0.30, 'name': 'L3'},
        {'bbox': (75, 425, 990, 490),   'start': 1.5,  'reveal_dur': 0.30, 'name': 'L4'},
        # Black double-line underline below the $50 column
        {'bbox': (575, 502, 990, 530),  'start': 2.0,  'reveal_dur': 0.30, 'name': 'underline'},
        # every month: = $438
        {'bbox': (75, 548, 990, 620),   'start': 2.05, 'reveal_dur': 0.40, 'name': 'every_month'},
        # × 12 months
        {'bbox': (75, 658, 580, 720),   'start': 2.5,  'reveal_dur': 0.45, 'name': 'x12_months'},
        # $5,256/year text (narrower bbox so ellipse outline stays masked here)
        {'bbox': (200, 730, 870, 850),  'start': 3.0,  'reveal_dur': 0.50, 'name': '5256_year'},
        # Green arrow (tip extends above bbox)
        {'bbox': (450, 855, 600, 950),  'start': 4.0,  'reveal_dur': 0.45, 'name': 'arrow'},
        # vs. one custom app you OWN
        {'bbox': (200, 960, 880, 1015), 'start': 4.5,  'reveal_dur': 0.45, 'name': 'vs_text'},
    ]

    # Ellipse bbox (around $5,256/year). Animates separately via sweep starting at 3.5s.
    ellipse_bbox = (115, 712, 950, 870)

    masked_base = src_orig.copy()
    draw_m = ImageDraw.Draw(masked_base)
    for el in elements:
        x1, y1, x2, y2 = el['bbox']
        draw_m.rectangle([(x1, y1), (x2, y2)], fill=bg_color)
    # Mask the whole ellipse area too — its content is revealed later via sweep
    ex1, ey1, ex2, ey2 = ellipse_bbox
    draw_m.rectangle([(ex1, ey1), (ex2, ey2)], fill=bg_color)
    # Re-overlay $5,256/year text area as bg-masked too (since ellipse_bbox covers it)
    # Then $5,256/year reveal will paint text back in via its own element above.

    # Pre-compute a transparent RGBA overlay containing ONLY the red ellipse pixels
    # (so per-frame sweep can use a simple mask multiply instead of per-pixel scans)
    ellipse_crop_rgb = src_orig.crop(ellipse_bbox).convert('RGB')
    cw, ch = ellipse_crop_rgb.size
    ellipse_red_overlay = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
    ecp_src = ellipse_crop_rgb.load()
    ecp_dst = ellipse_red_overlay.load()
    for yy in range(ch):
        for xx in range(cw):
            r, g, b = ecp_src[xx, yy]
            if r > 130 and g < 95 and b < 95 and r - max(g, b) > 40 and abs(int(g) - int(b)) < 25:
                ecp_dst[xx, yy] = (r, g, b, 255)

    # Always-visible: top/bottom strips, "Monthly cost:", ecdautomation.com — those stay from masked_base

    print(f'  rendering {TOTAL_FRAMES} frames...')
    for i in range(TOTAL_FRAMES):
        t = i / FPS
        frame = masked_base.copy()

        for el in elements:
            start = el['start']
            dur = el['reveal_dur']
            if t < start:
                continue
            x1, y1, x2, y2 = el['bbox']
            p = min(1.0, (t - start) / dur)
            ease = ease_out_cubic(p)

            # Most elements: write-on left-to-right reveal (clip horizontally)
            # For "5256_year": vertical scale-in plus content reveal (slightly more dramatic)
            content = src_orig.crop((x1, y1, x2, y2))
            mask = Image.new('L', content.size, 0)
            mdraw = ImageDraw.Draw(mask)
            if el['name'] == 'arrow':
                # Top-to-bottom wipe for arrow
                w, h = content.size
                reveal_h = int(h * ease)
                mdraw.rectangle([(0, 0), (w, reveal_h)], fill=255)
            elif el['name'] == '5256_year':
                # Soft fade + slight scale
                w, h = content.size
                alpha_val = int(255 * ease)
                mdraw.rectangle([(0, 0), (w, h)], fill=alpha_val)
            else:
                # Left-to-right wipe
                w, h = content.size
                reveal_w = int(w * ease)
                mdraw.rectangle([(0, 0), (reveal_w, h)], fill=255)

            # Composite content onto frame using the mask
            frame.paste(content, (x1, y1), mask)

        # Red ellipse — clockwise sweep starting from the top (t=3.5s, 0.5s draw)
        if t >= 3.5:
            ellipse_p = min(1.0, (t - 3.5) / 0.5)
            ease_e = ease_out_cubic(ellipse_p)
            sweep_angle = ease_e * 360
            # Build sweep mask (pieslice from -90deg clockwise)
            sweep_mask = Image.new('L', (cw, ch), 0)
            ImageDraw.Draw(sweep_mask).pieslice(
                [(-50, -50), (cw + 50, ch + 50)], -90, -90 + sweep_angle, fill=255
            )
            # Combine sweep with pre-computed red overlay alpha
            overlay_a = ellipse_red_overlay.split()[3]
            combined_a = ImageChops.multiply(overlay_a, sweep_mask)
            shown = ellipse_red_overlay.copy()
            shown.putalpha(combined_a)
            frame_rgba = frame.convert('RGBA')
            frame_rgba.alpha_composite(shown, (ellipse_bbox[0], ellipse_bbox[1]))
            frame = frame_rgba.convert('RGB')

        frame.save(os.path.join(frames_dir, f'frame_{i:04d}.png'),
                   optimize=False, compress_level=1)

    out = os.path.join(ADS_DIR, 'ecd_ad3_whiteboard.mp4')
    print(f'  encoding -> {out}')
    encode_mp4(frames_dir, out)
    return out


# ============================================================
# VERTICAL (1080x1920) HELPERS — for Meta Reels/Stories
# ============================================================
# Layout: 420px top pad + 1080px original content + 420px bottom pad
# Reels UI covers top 250px and bottom 250px of the canvas, so:
#   Top text safe zone: full-canvas y=250-420  (= panel y=250-420)
#   Bottom text safe zone: full-canvas y=1500-1670  (= bottom panel y=0-170)

V_W = 1080
V_H = 1920
V_TOP_PAD_H = 420
V_BOTTOM_PAD_H = 420
V_CONTENT_Y = V_TOP_PAD_H  # 420; square content goes here


def make_panel(width, height, bg_color, lines):
    """Render a padding panel with stacked text lines.
    lines: list of {'text', 'y', 'size', 'weight', 'color', 'align'}.
    y is relative to the panel top. align defaults to 'center'.
    """
    panel = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(panel)
    for L in lines:
        f = F(L['size'], L.get('weight', 'medium'))
        bbox = draw.textbbox((0, 0), L['text'], font=f)
        text_w = bbox[2] - bbox[0]
        if L.get('align', 'center') == 'center':
            x = (width - text_w) // 2
        else:
            x = 60
        draw.text((x, L['y']), L['text'], font=f, fill=L['color'])
    return panel


def wrap_to_vertical(square_frame, top_panel, bottom_panel):
    """Compose a 1080x1920 canvas: top_panel / square content / bottom_panel."""
    canvas = Image.new('RGB', (V_W, V_H), (0, 0, 0))
    canvas.paste(top_panel, (0, 0))
    canvas.paste(square_frame, (0, V_CONTENT_Y))
    canvas.paste(bottom_panel, (0, V_CONTENT_Y + 1080))
    return canvas


# ============================================================
# AD 1 VERTICAL
# ============================================================

def build_ad1_vertical():
    print('\n=== AD 1 VERTICAL: Receipt ===')
    frames_dir = os.path.join(TMP_DIR, 'ad1v')
    if os.path.exists(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir, exist_ok=True)

    stamp_overlay, stamp_x, stamp_y, stamp_cx, stamp_cy = extract_stamp_from_ad1()
    clean_base = build_clean_receipt()
    stamped_orig = Image.open(os.path.join(ADS_DIR, 'ecd_ad1_receipt.png')).convert('RGB')
    sw, sh = stamp_overlay.size
    stamp_local_cx = stamp_cx - stamp_x
    stamp_local_cy = stamp_cy - stamp_y
    cta_y1, cta_y2 = 920, 1020

    PAD_BG = (255, 255, 255)
    ACCENT = (194, 65, 12)  # matches site --color-accent
    top_panel = make_panel(V_W, V_TOP_PAD_H, PAD_BG, [
        {'text': 'Cancel This.',         'y': 245, 'size': 92, 'weight': 'bold',   'color': (15, 15, 15)},
        {'text': 'Your software stack.', 'y': 352, 'size': 48, 'weight': 'medium', 'color': (90, 90, 90)},
    ])
    bottom_panel = make_panel(V_W, V_BOTTOM_PAD_H, PAD_BG, [
        {'text': 'Build a custom app you OWN', 'y': 25,  'size': 54, 'weight': 'bold',   'color': (15, 15, 15)},
        {'text': 'ecdautomation.com',          'y': 102, 'size': 44, 'weight': 'medium', 'color': ACCENT},
    ])

    print(f'  rendering {TOTAL_FRAMES} frames...')
    for i in range(TOTAL_FRAMES):
        t = i / FPS

        if t < 1.5:
            frame = clean_base.copy()
        elif t < 2.0:
            p = (t - 1.5) / 0.5
            ease = ease_out_cubic(p)
            scale = lerp(1.3, 1.0, ease)
            alpha = lerp(0.3, 1.0, ease)
            shake_x = shake_y = 0
            if p > 0.8:
                sp = (p - 0.8) / 0.2
                damp = 1 - sp
                shake_x = int(math.sin(sp * 25) * 6 * damp)
                shake_y = int(math.cos(sp * 28) * 3 * damp)
            new_w = max(1, int(sw * scale))
            new_h = max(1, int(sh * scale))
            scaled = stamp_overlay.resize((new_w, new_h), Image.LANCZOS)
            if alpha < 1.0:
                a = scaled.split()[3].point(lambda px: int(px * alpha))
                scaled.putalpha(a)
            px = int(stamp_cx - new_w * (stamp_local_cx / sw)) + shake_x
            py = int(stamp_cy - new_h * (stamp_local_cy / sh)) + shake_y
            frame = clean_base.copy()
            frame_rgba = frame.convert('RGBA')
            frame_rgba.alpha_composite(scaled, (px, py))
            frame = frame_rgba.convert('RGB')
        elif t < 4.0:
            frame = stamped_orig.copy()
        else:
            frame = stamped_orig.copy()
            pt = (t - 4.0) / 1.0
            pulse = 1.0 + 0.02 * math.sin(pt * math.pi * 2) * math.sin(pt * math.pi)
            cta_w = 1080
            cta_h = cta_y2 - cta_y1
            cta = frame.crop((0, cta_y1, cta_w, cta_y2))
            new_w = int(cta_w * pulse)
            new_h = int(cta_h * pulse)
            cta_scaled = cta.resize((new_w, new_h), Image.LANCZOS)
            ImageDraw.Draw(frame).rectangle([(0, cta_y1 - 4), (cta_w, cta_y2 + 4)], fill=(255, 255, 255))
            cta_center_y = (cta_y1 + cta_y2) // 2
            px = (cta_w - new_w) // 2
            py = cta_center_y - new_h // 2
            frame.paste(cta_scaled, (px, py))

        vertical = wrap_to_vertical(frame, top_panel, bottom_panel)
        vertical.save(os.path.join(frames_dir, f'frame_{i:04d}.png'),
                      optimize=False, compress_level=1)

    out = os.path.join(ADS_DIR, 'ecd_ad1_receipt_vertical.mp4')
    print(f'  encoding -> {out}')
    encode_mp4(frames_dir, out)
    return out


# ============================================================
# AD 2 VERTICAL
# ============================================================

def build_ad2_vertical():
    print('\n=== AD 2 VERTICAL: Text Message ===')
    frames_dir = os.path.join(TMP_DIR, 'ad2v')
    if os.path.exists(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir, exist_ok=True)

    src_orig = Image.open(os.path.join(ADS_DIR, 'ecd_ad2_textmessage.png')).convert('RGB')

    bubbles = [
        {'bbox': (40, 270, 525, 400),   'side': 'L', 'enter_t': 0.5},
        {'bbox': (570, 420, 1040, 605), 'side': 'R', 'enter_t': 1.5},
        {'bbox': (40, 625, 525, 720),   'side': 'L', 'enter_t': 2.5},
        {'bbox': (560, 740, 1040, 970), 'side': 'R', 'enter_t': 3.5},
    ]
    for b in bubbles:
        b['img'] = src_orig.crop(b['bbox']).convert('RGBA')

    empty_base = src_orig.copy()
    d = ImageDraw.Draw(empty_base)
    for b in bubbles:
        x1, y1, x2, y2 = b['bbox']
        d.rectangle([(x1 - 12, y1 - 12), (x2 + 12, y2 + 12)], fill=(0, 0, 0))

    def render_typing_bubble(side):
        bub_w, bub_h = 130, 65
        img = Image.new('RGBA', (bub_w, bub_h), (0, 0, 0, 0))
        dd = ImageDraw.Draw(img)
        bg = (60, 60, 60, 255) if side == 'L' else (10, 120, 230, 255)
        dd.rounded_rectangle([(0, 0), (bub_w, bub_h)], radius=24, fill=bg)
        for k in range(3):
            cx = 32 + k * 32
            cy = bub_h // 2
            dd.ellipse([(cx - 7, cy - 7), (cx + 7, cy + 7)], fill=(180, 180, 180, 255))
        return img

    typing_L = render_typing_bubble('L')
    typing_R = render_typing_bubble('R')

    PAD_BG = (0, 0, 0)
    ACCENT_BLUE = (100, 180, 255)
    top_panel = make_panel(V_W, V_TOP_PAD_H, PAD_BG, [
        {'text': 'When your friend cancels',     'y': 245, 'size': 48, 'weight': 'medium', 'color': (220, 220, 220)},
        {'text': 'GoHighLevel…',            'y': 318, 'size': 64, 'weight': 'bold',   'color': (255, 255, 255)},
    ])
    bottom_panel = make_panel(V_W, V_BOTTOM_PAD_H, PAD_BG, [
        {'text': 'Custom CRM. You own it. 14 days.', 'y': 18,  'size': 46, 'weight': 'bold',   'color': (255, 255, 255)},
        {'text': 'ecdautomation.com',                 'y': 96,  'size': 44, 'weight': 'medium', 'color': ACCENT_BLUE},
    ])

    print(f'  rendering {TOTAL_FRAMES} frames...')
    for i in range(TOTAL_FRAMES):
        t = i / FPS
        frame = empty_base.copy().convert('RGBA')

        for b in bubbles:
            et = b['enter_t']
            slide_dur = 0.35
            typing_dur = 0.30
            typing_start = et - typing_dur
            if typing_start <= t < et:
                ti = typing_L if b['side'] == 'L' else typing_R
                tx = b['bbox'][0] if b['side'] == 'L' else (b['bbox'][2] - ti.size[0])
                ty = b['bbox'][1] + 8
                pulse = 0.55 + 0.45 * abs(math.sin((t - typing_start) * 8))
                ti_copy = ti.copy()
                a = ti_copy.split()[3].point(lambda p: int(p * pulse))
                ti_copy.putalpha(a)
                frame.alpha_composite(ti_copy, (tx, ty))
            if t >= et:
                slide_p = min(1.0, (t - et) / slide_dur)
                ease = ease_out_cubic(slide_p)
                if b['side'] == 'L':
                    y_offset = int((1 - ease) * 80)
                    x_offset = 0
                else:
                    x_offset = int((1 - ease) * 200)
                    y_offset = int((1 - ease) * 30)
                alpha = lerp(0.5, 1.0, ease) if slide_p < 1 else 1.0
                x1, y1, _, _ = b['bbox']
                img = b['img']
                if alpha < 1.0:
                    img_copy = img.copy()
                    a = img_copy.split()[3].point(lambda p: int(p * alpha))
                    img_copy.putalpha(a)
                    frame.alpha_composite(img_copy, (x1 + x_offset, y1 + y_offset))
                else:
                    frame.alpha_composite(img, (x1 + x_offset, y1 + y_offset))

        square = frame.convert('RGB')
        vertical = wrap_to_vertical(square, top_panel, bottom_panel)
        vertical.save(os.path.join(frames_dir, f'frame_{i:04d}.png'),
                      optimize=False, compress_level=1)

    out = os.path.join(ADS_DIR, 'ecd_ad2_textmessage_vertical.mp4')
    print(f'  encoding -> {out}')
    encode_mp4(frames_dir, out)
    return out


# ============================================================
# AD 3 VERTICAL
# ============================================================

def build_ad3_vertical():
    print('\n=== AD 3 VERTICAL: Whiteboard ===')
    frames_dir = os.path.join(TMP_DIR, 'ad3v')
    if os.path.exists(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir, exist_ok=True)

    src_orig = Image.open(os.path.join(ADS_DIR, 'ecd_ad3_whiteboard.png')).convert('RGB')
    bg_color = src_orig.getpixel((30, 30))

    elements = [
        {'bbox': (75, 155, 990, 230),   'start': 0.3,  'reveal_dur': 0.30, 'name': 'L1'},
        {'bbox': (75, 245, 990, 320),   'start': 0.7,  'reveal_dur': 0.30, 'name': 'L2'},
        {'bbox': (75, 335, 990, 400),   'start': 1.1,  'reveal_dur': 0.30, 'name': 'L3'},
        {'bbox': (75, 425, 990, 490),   'start': 1.5,  'reveal_dur': 0.30, 'name': 'L4'},
        {'bbox': (575, 502, 990, 530),  'start': 2.0,  'reveal_dur': 0.30, 'name': 'underline'},
        {'bbox': (75, 548, 990, 620),   'start': 2.05, 'reveal_dur': 0.40, 'name': 'every_month'},
        {'bbox': (75, 658, 580, 720),   'start': 2.5,  'reveal_dur': 0.45, 'name': 'x12_months'},
        {'bbox': (200, 730, 870, 850),  'start': 3.0,  'reveal_dur': 0.50, 'name': '5256_year'},
        {'bbox': (450, 855, 600, 950),  'start': 4.0,  'reveal_dur': 0.45, 'name': 'arrow'},
        {'bbox': (200, 960, 880, 1015), 'start': 4.5,  'reveal_dur': 0.45, 'name': 'vs_text'},
    ]
    ellipse_bbox = (115, 712, 950, 870)
    masked_base = src_orig.copy()
    dm = ImageDraw.Draw(masked_base)
    for el in elements:
        x1, y1, x2, y2 = el['bbox']
        dm.rectangle([(x1, y1), (x2, y2)], fill=bg_color)
    dm.rectangle([(ellipse_bbox[0], ellipse_bbox[1]),
                  (ellipse_bbox[2], ellipse_bbox[3])], fill=bg_color)

    ellipse_crop_rgb = src_orig.crop(ellipse_bbox).convert('RGB')
    cw, ch = ellipse_crop_rgb.size
    ellipse_red_overlay = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
    ecp_src = ellipse_crop_rgb.load()
    ecp_dst = ellipse_red_overlay.load()
    for yy in range(ch):
        for xx in range(cw):
            r, g, b = ecp_src[xx, yy]
            if r > 130 and g < 95 and b < 95 and r - max(g, b) > 40 and abs(int(g) - int(b)) < 25:
                ecp_dst[xx, yy] = (r, g, b, 255)

    # Vertical padding panels
    PAD_BG = bg_color
    GREEN = (34, 134, 58)
    top_panel = make_panel(V_W, V_TOP_PAD_H, PAD_BG, [
        {'text': 'The cost of renting',  'y': 245, 'size': 56, 'weight': 'bold', 'color': (25, 25, 25)},
        {'text': 'your software stack:', 'y': 322, 'size': 56, 'weight': 'bold', 'color': (25, 25, 25)},
    ])
    bottom_panel = make_panel(V_W, V_BOTTOM_PAD_H, PAD_BG, [
        {'text': 'vs. one custom app you OWN', 'y': 18,  'size': 50, 'weight': 'bold',   'color': GREEN},
        {'text': 'ecdautomation.com — $5K, 14 days, yours forever', 'y': 100, 'size': 30, 'weight': 'medium', 'color': (90, 90, 90)},
    ])

    print(f'  rendering {TOTAL_FRAMES} frames...')
    for i in range(TOTAL_FRAMES):
        t = i / FPS
        frame = masked_base.copy()

        for el in elements:
            if t < el['start']:
                continue
            x1, y1, x2, y2 = el['bbox']
            p = min(1.0, (t - el['start']) / el['reveal_dur'])
            ease = ease_out_cubic(p)
            content = src_orig.crop((x1, y1, x2, y2))
            mask = Image.new('L', content.size, 0)
            mdraw = ImageDraw.Draw(mask)
            w, h = content.size
            if el['name'] == 'arrow':
                mdraw.rectangle([(0, 0), (w, int(h * ease))], fill=255)
            elif el['name'] == '5256_year':
                mdraw.rectangle([(0, 0), (w, h)], fill=int(255 * ease))
            else:
                mdraw.rectangle([(0, 0), (int(w * ease), h)], fill=255)
            frame.paste(content, (x1, y1), mask)

        if t >= 3.5:
            ellipse_p = min(1.0, (t - 3.5) / 0.5)
            ease_e = ease_out_cubic(ellipse_p)
            sweep_angle = ease_e * 360
            sweep_mask = Image.new('L', (cw, ch), 0)
            ImageDraw.Draw(sweep_mask).pieslice(
                [(-50, -50), (cw + 50, ch + 50)], -90, -90 + sweep_angle, fill=255
            )
            overlay_a = ellipse_red_overlay.split()[3]
            combined_a = ImageChops.multiply(overlay_a, sweep_mask)
            shown = ellipse_red_overlay.copy()
            shown.putalpha(combined_a)
            frame_rgba = frame.convert('RGBA')
            frame_rgba.alpha_composite(shown, (ellipse_bbox[0], ellipse_bbox[1]))
            frame = frame_rgba.convert('RGB')

        vertical = wrap_to_vertical(frame, top_panel, bottom_panel)
        vertical.save(os.path.join(frames_dir, f'frame_{i:04d}.png'),
                      optimize=False, compress_level=1)

    out = os.path.join(ADS_DIR, 'ecd_ad3_whiteboard_vertical.mp4')
    print(f'  encoding -> {out}')
    encode_mp4(frames_dir, out)
    return out


# ============================================================
# MAIN
# ============================================================

def main():
    os.makedirs(TMP_DIR, exist_ok=True)
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'

    outs = []
    if which in ('all', '1'):
        outs.append(build_ad1())
    if which in ('all', '2'):
        outs.append(build_ad2())
    if which in ('all', '3'):
        outs.append(build_ad3())
    if which in ('vall', 'v1'):
        outs.append(build_ad1_vertical())
    if which in ('vall', 'v2'):
        outs.append(build_ad2_vertical())
    if which in ('vall', 'v3'):
        outs.append(build_ad3_vertical())

    print('\n=== OUTPUTS ===')
    for o in outs:
        sz = os.path.getsize(o)
        print(f'  {o}  {sz/1024/1024:.2f} MB')


if __name__ == '__main__':
    main()
