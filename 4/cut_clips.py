"""
Cut exported video clips from folder 3 using durations from folder 2.

Default:
    python 4/cut_clips.py

Fast stream-copy mode:
    python 4/cut_clips.py --mode copy

Vertical short-form export:
    python 4/cut_clips.py --resize vertical
"""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DURATIONS = ROOT / "2" / "clip_durations.txt"
DEFAULT_VIDEO_DIR = ROOT / "3" / "downloads"
DEFAULT_OUTPUT_DIR = ROOT / "4" / "clips"


TIME_RE = re.compile(
    r"Time:\s*(?P<start>\d{2}:\d{2}:\d{2}(?:[,.]\d{1,3})?)\s*-\s*"
    r"(?P<end>\d{2}:\d{2}:\d{2}(?:[,.]\d{1,3})?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClipDuration:
    number: int
    start: str
    end: str


def parse_time_to_seconds(value: str) -> float:
    value = value.replace(",", ".")
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def seconds_to_duration(start: str, end: str) -> str:
    duration = parse_time_to_seconds(end) - parse_time_to_seconds(start)
    if duration <= 0:
        raise ValueError(f"Invalid clip range: {start} - {end}")
    return f"{duration:.3f}"


def parse_clip_durations(path: Path) -> list[ClipDuration]:
    text = path.read_text(encoding="utf-8")
    matches = list(TIME_RE.finditer(text))
    if not matches:
        raise ValueError(f"No clip times found in {path}")

    return [
        ClipDuration(number=index + 1, start=match.group("start"), end=match.group("end"))
        for index, match in enumerate(matches)
    ]


def find_source_video(video_dir: Path) -> Path:
    videos = sorted(
        video_dir.glob("*.mp4"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not videos:
        raise FileNotFoundError(f"No .mp4 source video found in {video_dir}")
    return videos[0]


def resize_filter(mode: str) -> str | None:
    if mode == "none":
        return None
    if mode == "vertical":
        return (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920"
        )
    if mode == "vertical-pad":
        return (
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
        )
    if mode == "horizontal":
        return (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
        )
    raise ValueError(f"Unsupported resize mode: {mode}")


def build_ffmpeg_command(
    source: Path,
    output: Path,
    clip: ClipDuration,
    mode: str,
    resize: str,
) -> list[str]:
    duration = seconds_to_duration(clip.start, clip.end)
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-ss",
        clip.start,
        "-i",
        str(source),
        "-t",
        duration,
    ]

    vf = resize_filter(resize)

    if mode == "copy" and vf is None:
        command += [
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
        ]
    else:
        if vf:
            command += ["-vf", vf]
        command += [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
        ]

    command.append(str(output))
    return command


def export_clips(
    source: Path,
    clips: list[ClipDuration],
    output_dir: Path,
    mode: str,
    resize: str,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []

    for clip in clips:
        output = output_dir / f"clip_{clip.number:02d}.mp4"
        command = build_ffmpeg_command(source, output, clip, mode=mode, resize=resize)
        print(f"Exporting {output.name}: {clip.start} - {clip.end}")
        subprocess.run(command, check=True)
        outputs.append(output)

    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cut clips from the downloaded source video using folder 2 durations."
    )
    parser.add_argument("--durations", type=Path, default=DEFAULT_DURATIONS)
    parser.add_argument("--video", type=Path, help="Specific source video path.")
    parser.add_argument("--video-dir", type=Path, default=DEFAULT_VIDEO_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--mode",
        choices=("accurate", "copy"),
        default="accurate",
        help="accurate re-encodes clips; copy is fastest but may cut on nearby keyframes.",
    )
    parser.add_argument(
        "--resize",
        choices=("none", "vertical", "vertical-pad", "horizontal"),
        default="none",
        help="Optional resize/export format.",
    )
    args = parser.parse_args()

    clips = parse_clip_durations(args.durations)
    source = args.video if args.video else find_source_video(args.video_dir)
    outputs = export_clips(
        source=source,
        clips=clips,
        output_dir=args.output_dir,
        mode=args.mode,
        resize=args.resize,
    )

    print("Done.")
    for output in outputs:
        print(output)


if __name__ == "__main__":
    main()
