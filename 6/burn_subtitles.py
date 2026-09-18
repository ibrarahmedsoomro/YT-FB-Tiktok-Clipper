"""
Burn styled subtitles into the vertical clips from folder 5.

Input:
    5/vertical_clips/clip_XX.mp4   — vertical clips (output of step 5)
    1/*.srt                         — original subtitle file with timestamps
    2/clip_durations.txt            — clip time ranges for timestamp offsetting

Output:
    6/captioned_clips/clip_XX.mp4  — final captioned clips ready for TikTok / Shorts

Styles:
    1 — TikTok Classic   bold white text, thick black outline
    2 — Word Pop         yellow text on dark semi-transparent box
    3 — Podcast Modern   clean white text with soft drop shadow
    4 — Word-by-Word     one word at a time, karaoke-style timing

Usage:
    python 6/burn_subtitles.py --style 1
    python 6/burn_subtitles.py --style 2 --clip 1
    python 6/burn_subtitles.py --style 3
    python 6/burn_subtitles.py --style 4 --clip 2
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VERTICAL_DIR = ROOT / "5" / "vertical_clips"
DEFAULT_OUTPUT_DIR   = ROOT / "6" / "captioned_clips"
DEFAULT_DURATIONS    = ROOT / "2" / "clip_durations.txt"
DEFAULT_SRT_DIR      = ROOT / "1"


# ---------------------------------------------------------------------------
# Caption style definitions
# ---------------------------------------------------------------------------

STYLES: dict[int, dict] = {
    1: {
        "name": "TikTok Classic",
        "description": "Bold white text with thick black outline — the iconic TikTok look.",
        "force_style": (
            "FontName=Arial Black,"
            "FontSize=22,"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "Outline=4,"
            "Bold=1,"
            "Alignment=2,"
            "MarginV=120"
        ),
        "word_by_word": False,
    },
    2: {
        "name": "Word Pop",
        "description": "Yellow text on a dark semi-transparent background box.",
        "force_style": (
            "FontName=Impact,"
            "FontSize=20,"
            "PrimaryColour=&H0000FFFF,"
            "BackColour=&H88000000,"
            "BorderStyle=3,"
            "Bold=1,"
            "Alignment=2,"
            "MarginV=140"
        ),
        "word_by_word": False,
    },
    3: {
        "name": "Podcast Modern",
        "description": "Clean white text with a soft drop shadow — minimal and premium.",
        "force_style": (
            "FontName=Arial,"
            "FontSize=18,"
            "PrimaryColour=&H00FFFFFF,"
            "Shadow=2,"
            "BackColour=&HAA000000,"
            "BorderStyle=1,"
            "Bold=0,"
            "Alignment=2,"
            "MarginV=130"
        ),
        "word_by_word": False,
    },
    4: {
        "name": "Word-by-Word",
        "description": "One word pops up at a time in sync with speech — viral karaoke style.",
        "force_style": (
            "FontName=Arial Black,"
            "FontSize=24,"
            "PrimaryColour=&H0000FFFF,"
            "OutlineColour=&H00000000,"
            "Outline=3,"
            "Bold=1,"
            "Alignment=2,"
            "MarginV=120"
        ),
        "word_by_word": True,
    },
}

STYLE_MENU = """
Available subtitle styles:

  1 — TikTok Classic
      Bold white text, thick black outline.
      The standard high-readability TikTok look.

  2 — Word Pop
      Yellow text on a dark semi-transparent background box.
      Great for punchy interview or reaction clips.

  3 — Podcast Modern
      Clean white text with a soft drop shadow.
      Minimal and premium — ideal for talking-head content.

  4 — Word-by-Word
      One word appears at a time in sync with speech.
      Viral karaoke-style — the fastest-growing caption trend.
"""


# ---------------------------------------------------------------------------
# SRT parsing
# ---------------------------------------------------------------------------

_TS_RE = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})")
_CLIP_RANGE_RE = re.compile(
    r"Time:\s*(?P<start>\d{2}:\d{2}:\d{2}(?:[,.]\d{1,3})?)\s*-\s*"
    r"(?P<end>\d{2}:\d{2}:\d{2}(?:[,.]\d{1,3})?)",
    re.IGNORECASE,
)


@dataclass
class Cue:
    index: int
    start: float   # seconds
    end: float     # seconds
    text: str


def _parse_ts(ts: str) -> float:
    m = _TS_RE.search(ts)
    if not m:
        raise ValueError(f"Cannot parse timestamp: {ts!r}")
    h, mn, s, ms = (int(x) for x in m.groups())
    return h * 3600 + mn * 60 + s + ms / 1000.0


def _fmt_ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = round((seconds % 1) * 1000)
    if ms >= 1000:
        ms, s = 0, s + 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt(path: Path) -> list[Cue]:
    """Parse an SRT file into a list of Cue objects."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n\s*\n", raw.strip())
    cues: list[Cue] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        # Skip optional cue index number
        i = 1 if lines[0].isdigit() else 0
        if i >= len(lines) or "-->" not in lines[i]:
            continue
        parts = lines[i].split("-->", 1)
        try:
            start = _parse_ts(parts[0])
            end = _parse_ts(parts[1])
        except ValueError:
            continue
        text = " ".join(lines[i + 1:])
        # Strip HTML/VTT tags
        text = re.sub(r"<[^>]+>", "", text).strip()
        if text:
            cues.append(Cue(index=len(cues) + 1, start=start, end=end, text=text))
    return cues


def parse_clip_ranges(path: Path) -> list[tuple[float, float]]:
    """Read clip start/end times from clip_durations.txt."""
    raw = path.read_text(encoding="utf-8")
    ranges: list[tuple[float, float]] = []
    for m in _CLIP_RANGE_RE.finditer(raw):
        def to_sec(s: str) -> float:
            s = s.replace(",", ".")
            parts = s.split(":")
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        ranges.append((to_sec(m.group("start")), to_sec(m.group("end"))))
    return ranges


def find_srt(srt_dir: Path) -> Path:
    """Find the best SRT file in the given directory."""
    srts = sorted(srt_dir.glob("*.srt"))
    if not srts:
        raise FileNotFoundError(f"No .srt file found in {srt_dir}")
    # Prefer manually-uploaded subtitles over auto-generated
    manual = [s for s in srts if "orig" in s.stem or "manual" in s.stem]
    return manual[0] if manual else srts[0]


# ---------------------------------------------------------------------------
# Subtitle processing
# ---------------------------------------------------------------------------

def trim_and_offset(cues: list[Cue], clip_start: float, clip_end: float) -> list[Cue]:
    """
    Filter cues that overlap [clip_start, clip_end] and offset timestamps
    so the clip begins at 00:00:00.
    """
    result: list[Cue] = []
    for cue in cues:
        if cue.end <= clip_start or cue.start >= clip_end:
            continue
        result.append(Cue(
            index=len(result) + 1,
            start=max(cue.start - clip_start, 0.0),
            end=min(cue.end - clip_start, clip_end - clip_start),
            text=cue.text,
        ))
    return result


def split_words(cues: list[Cue]) -> list[Cue]:
    """
    Split each cue into individual word-timed sub-cues.
    Cue duration is divided equally among the words.
    """
    result: list[Cue] = []
    for cue in cues:
        words = cue.text.split()
        if not words:
            continue
        word_dur = (cue.end - cue.start) / len(words)
        for i, word in enumerate(words):
            result.append(Cue(
                index=len(result) + 1,
                start=cue.start + i * word_dur,
                end=cue.start + (i + 1) * word_dur,
                text=word,
            ))
    return result


def write_srt(cues: list[Cue], path: Path) -> None:
    lines: list[str] = []
    for cue in cues:
        lines += [
            str(cue.index),
            f"{_fmt_ts(cue.start)} --> {_fmt_ts(cue.end)}",
            cue.text,
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# FFmpeg helpers
# ---------------------------------------------------------------------------

def _ffmpeg_path(path: Path) -> str:
    """
    Convert an absolute path to a form safe for FFmpeg's subtitles filter.
    On Windows the drive-letter colon must be escaped as \\: and backslashes
    replaced with forward slashes.
    """
    s = str(path.resolve()).replace("\\", "/")
    # Escape Windows drive letter: C:/ -> C\:/
    s = re.sub(r"^([A-Za-z]):/", r"\1\\:/", s)
    return s


def build_ffmpeg_cmd(
    source: Path,
    output: Path,
    srt_path: Path,
    force_style: str,
) -> list[str]:
    escaped_srt = _ffmpeg_path(srt_path)
    vf = f"subtitles='{escaped_srt}':force_style='{force_style}'"
    return [
        "ffmpeg", "-y", "-hide_banner",
        "-i", str(source),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(output),
    ]


# ---------------------------------------------------------------------------
# Per-clip processing
# ---------------------------------------------------------------------------

def process_clip(
    clip_num: int,
    source: Path,
    output: Path,
    all_cues: list[Cue],
    ranges: list[tuple[float, float]],
    style: dict,
    output_dir: Path,
) -> None:
    if clip_num > len(ranges):
        print(f"  [SKIP] No clip range #{clip_num} in clip_durations.txt.")
        return

    clip_start, clip_end = ranges[clip_num - 1]
    cues = trim_and_offset(all_cues, clip_start, clip_end)

    if not cues:
        print(
            f"  [WARN] No subtitle cues overlap clip {clip_num:02d} "
            f"({clip_start:.1f}s\u2013{clip_end:.1f}s). Copying without subtitles."
        )
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-i", str(source), "-c", "copy", str(output)],
            check=True,
        )
        return

    if style["word_by_word"]:
        cues = split_words(cues)

    # Write the trimmed subtitle track alongside the output (cleaned up after render)
    temp_srt = output_dir / f"_sub_clip_{clip_num:02d}.srt"
    write_srt(cues, temp_srt)

    try:
        cmd = build_ffmpeg_cmd(source, output, temp_srt, style["force_style"])
        print(f"  Burning [{style['name']}] into {output.name} ...")
        subprocess.run(cmd, check=True)
        print(f"  \u2713 Saved: {output.name}")
    finally:
        temp_srt.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Burn styled subtitles into vertical clips from folder 5.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=STYLE_MENU,
    )
    parser.add_argument(
        "--style",
        type=int,
        choices=list(STYLES.keys()),
        required=True,
        help="Caption style (1\u20134). Run without --style to see the menu.",
    )
    parser.add_argument(
        "--clip",
        default="all",
        help="Clip number to process, e.g. --clip 2. Default: all.",
    )
    parser.add_argument("--vertical-dir", type=Path, default=DEFAULT_VERTICAL_DIR)
    parser.add_argument("--output-dir",   type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--durations",    type=Path, default=DEFAULT_DURATIONS)
    parser.add_argument("--srt-dir",      type=Path, default=DEFAULT_SRT_DIR)
    args = parser.parse_args()

    style = STYLES[args.style]
    print(f"\n\u25b6  Style {args.style}: {style['name']}")
    print(f"   {style['description']}\n")

    # Load subtitle source
    srt_file = find_srt(args.srt_dir)
    print(f"SRT source  : {srt_file.name}")
    all_cues = parse_srt(srt_file)
    print(f"Cues loaded : {len(all_cues)}")

    # Load clip time ranges
    ranges = parse_clip_ranges(args.durations)
    print(f"Clip ranges : {len(ranges)}\n")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Discover vertical clips
    all_clips = sorted(args.vertical_dir.glob("clip_*.mp4"))
    if not all_clips:
        sys.exit(f"No vertical clips found in {args.vertical_dir}")

    if args.clip == "all":
        to_process = all_clips
    else:
        n = int(args.clip)
        to_process = [c for c in all_clips if re.search(rf"clip_{n:02d}", c.name)]
        if not to_process:
            sys.exit(f"clip_{n:02d}.mp4 not found in {args.vertical_dir}")

    for clip_path in to_process:
        m = re.search(r"clip_(\d+)", clip_path.stem)
        if not m:
            print(f"Skipping {clip_path.name} — cannot parse clip number.")
            continue
        clip_num = int(m.group(1))
        output = args.output_dir / clip_path.name
        print(f"[Clip {clip_num:02d}] {clip_path.name}")
        process_clip(
            clip_num=clip_num,
            source=clip_path,
            output=output,
            all_cues=all_cues,
            ranges=ranges,
            style=style,
            output_dir=args.output_dir,
        )

    print(f"\nAll done. Captioned clips saved to: {args.output_dir}")


if __name__ == "__main__":
    main()
