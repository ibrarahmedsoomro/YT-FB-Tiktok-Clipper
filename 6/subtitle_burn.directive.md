# Subtitle Burn Directive

**Step 6 of the clipping pipeline.**

Purpose: burn styled subtitles permanently into the vertical clips produced by folder `5`, creating the final deliverable clips ready for TikTok / YouTube Shorts.

---

## Input

| Source | Path |
|--------|------|
| Vertical clips | `5/vertical_clips/clip_XX.mp4` |
| Subtitle track | `1/*.srt` (original subtitle file with timestamps) |
| Clip time ranges | `2/clip_durations.txt` (used to trim and offset subtitle timestamps per clip) |

---

## MANDATORY PAUSE — Ask the User to Choose a Style

**Before running any command**, you MUST stop and present the four available caption styles to the user. Do not guess or assume a style. Do not proceed without an explicit choice.

Present this menu to the user word-for-word:

---

> **Please choose a subtitle style for your clips:**
>
> **1 — TikTok Classic**
> Bold white text with a thick black outline. The standard high-readability TikTok look.
>
> **2 — Word Pop**
> Yellow text on a dark semi-transparent background box. Great for punchy interview or reaction clips.
>
> **3 — Podcast Modern**
> Clean white text with a soft drop shadow. Minimal and premium — ideal for talking-head content.
>
> **4 — Word-by-Word**
> One word appears at a time in sync with speech. Viral karaoke-style — the fastest-growing TikTok caption trend.
>
> *Type 1, 2, 3, or 4 to continue.*

---

Wait for the user to reply. Do not proceed until a valid style number (1, 2, 3, or 4) is received.

---

## Running the Script

Once the user has chosen style `N`, run:

```bash
# Process all clips
python 6/burn_subtitles.py --style N

# Process a single clip only
python 6/burn_subtitles.py --style N --clip <clip_number>
```

Replace `N` with the user's chosen number.

---

## What the Script Does

1. Finds the `.srt` file in `1/` (prefers manually-uploaded subtitles over auto-generated).
2. Reads clip time ranges from `2/clip_durations.txt`.
3. For each vertical clip in `5/vertical_clips/`:
   - Trims the subtitle track to the clip's time window.
   - Offsets all cue timestamps so the clip starts at `00:00:00`.
   - For Style 4 only: splits each cue into individual word-timed entries.
   - Burns the styled subtitles into the video using FFmpeg's `subtitles` filter.
4. Saves the captioned clip to `6/captioned_clips/`.

---

## Expected Output

```
6/captioned_clips/clip_01.mp4
6/captioned_clips/clip_02.mp4
6/captioned_clips/clip_03.mp4
...
```

These are the **final deliverable clips** — subtitles permanently baked into every frame, ready for upload.

---

## Notes

- No subtitle re-download or re-analysis is needed. The `.srt` from folder `1` is reused directly.
- If no subtitle cues overlap a clip's time window, the clip is copied as-is and a warning is printed.
- Style 4 (Word-by-Word) divides each subtitle cue's duration equally among its words. For tighter per-word sync, ensure the `.srt` in folder `1` has short, frequently-updated cues — auto-generated captions typically produce these automatically.
- Do **not** re-download the video, re-run transcript extraction, or re-export clips in this step.
- Do **not** skip the style selection step. The user must always choose.
