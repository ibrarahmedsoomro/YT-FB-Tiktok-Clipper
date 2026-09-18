"""
Render vertical reframed clips from a fixed two-person interview source.

Default:
    python 5/active_speaker_reframe.py

Preview the planned speaker/crop segments without rendering:
    python 5/active_speaker_reframe.py --dry-run

Render a single clip:
    python 5/active_speaker_reframe.py --clip 1

Use manual speaker timing instead of automatic crop rotation:
    python 5/active_speaker_reframe.py --focus-mode timeline
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DURATIONS = ROOT / "2" / "clip_durations.txt"
DEFAULT_VIDEO_DIR = ROOT / "3" / "downloads"
DEFAULT_TIMELINE = ROOT / "5" / "speaker_timeline.csv"
DEFAULT_SPEAKERS = ROOT / "5" / "speakers.json"
DEFAULT_OUTPUT_DIR = ROOT / "5" / "vertical_clips"

TIME_RE = re.compile(
    r"Time:\s*(?P<start>\d{2}:\d{2}:\d{2}(?:[,.]\d{1,3})?)\s*-\s*"
    r"(?P<end>\d{2}:\d{2}:\d{2}(?:[,.]\d{1,3})?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClipRange:
    number: int
    start: float
    end: float


@dataclass(frozen=True)
class SpeakerSegment:
    start: float
    end: float
    speaker: str


@dataclass(frozen=True)
class CropBox:
    x: int
    y: int


@dataclass(frozen=True)
class SpeakerConfig:
    source_width: int | None
    source_height: int | None
    output_width: int
    output_height: int
    crop_width: int
    crop_height: int
    default_speaker: str
    speakers: dict[str, CropBox]


@dataclass(frozen=True)
class RotationConfig:
    primary_speaker: str
    secondary_speaker: str
    primary_min_seconds: float
    primary_max_seconds: float
    secondary_min_seconds: float
    secondary_max_seconds: float
    seed: int


def parse_time_to_seconds(value: str) -> float:
    value = value.strip().replace(",", ".")
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError(f"Expected HH:MM:SS timestamp, got {value!r}")
    hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def seconds_to_timestamp(value: float) -> str:
    if value < 0:
        raise ValueError(f"Timestamp cannot be negative: {value}")
    milliseconds = int(round(value * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def duration_seconds(start: float, end: float) -> float:
    duration = end - start
    if duration <= 0:
        raise ValueError(
            f"Invalid time range: {seconds_to_timestamp(start)} - {seconds_to_timestamp(end)}"
        )
    return duration


def parse_seconds_range(value: str) -> tuple[float, float]:
    value = value.strip()
    if not value:
        raise ValueError("Duration range cannot be empty")

    if "-" in value:
        raw_start, raw_end = value.split("-", maxsplit=1)
        start = float(raw_start.strip())
        end = float(raw_end.strip())
    else:
        start = end = float(value)

    if start <= 0 or end <= 0:
        raise ValueError(f"Duration range must be positive: {value!r}")
    if end < start:
        raise ValueError(f"Duration range end must be >= start: {value!r}")
    return start, end


def parse_clip_durations(path: Path) -> list[ClipRange]:
    text = path.read_text(encoding="utf-8")
    matches = list(TIME_RE.finditer(text))
    if not matches:
        raise ValueError(f"No clip times found in {path}")

    return [
        ClipRange(
            number=index + 1,
            start=parse_time_to_seconds(match.group("start")),
            end=parse_time_to_seconds(match.group("end")),
        )
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


def load_speaker_config(path: Path) -> SpeakerConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = [
        "output_width",
        "output_height",
        "crop_width",
        "crop_height",
        "default_speaker",
        "speakers",
    ]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"{path} is missing required keys: {', '.join(missing)}")

    speakers: dict[str, CropBox] = {}
    for name, box in data["speakers"].items():
        try:
            speakers[name] = CropBox(x=int(box["crop_x"]), y=int(box.get("crop_y", 0)))
        except KeyError as exc:
            raise ValueError(f"Speaker {name!r} is missing crop_x") from exc

    default_speaker = str(data["default_speaker"])
    if default_speaker not in speakers:
        raise ValueError(f"default_speaker {default_speaker!r} is not in speakers")

    return SpeakerConfig(
        source_width=int(data["source_width"]) if data.get("source_width") else None,
        source_height=int(data["source_height"]) if data.get("source_height") else None,
        output_width=int(data["output_width"]),
        output_height=int(data["output_height"]),
        crop_width=int(data["crop_width"]),
        crop_height=int(data["crop_height"]),
        default_speaker=default_speaker,
        speakers=speakers,
    )


def load_timeline(path: Path, known_speakers: set[str]) -> list[SpeakerSegment]:
    if not path.exists():
        return []

    rows: list[SpeakerSegment] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        filtered = (
            line
            for line in handle
            if line.strip() and not line.lstrip().startswith("#")
        )
        reader = csv.DictReader(filtered)
        expected = {"start", "end", "speaker"}
        if not reader.fieldnames:
            return []
        missing = expected - set(reader.fieldnames)
        if missing:
            raise ValueError(f"{path} is missing CSV columns: {', '.join(sorted(missing))}")

        for row_number, row in enumerate(reader, start=2):
            speaker = (row.get("speaker") or "").strip()
            if speaker not in known_speakers:
                raise ValueError(
                    f"{path}:{row_number} uses unknown speaker {speaker!r}. "
                    f"Known speakers: {', '.join(sorted(known_speakers))}"
                )
            start = parse_time_to_seconds(row["start"])
            end = parse_time_to_seconds(row["end"])
            duration_seconds(start, end)
            rows.append(SpeakerSegment(start=start, end=end, speaker=speaker))

    return sorted(rows, key=lambda segment: (segment.start, segment.end))


def probe_video(path: Path) -> tuple[int, int]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError(f"Could not read video dimensions from {path}")
    return int(streams[0]["width"]), int(streams[0]["height"])


def validate_config(config: SpeakerConfig, actual_width: int, actual_height: int) -> None:
    if config.source_width and config.source_width != actual_width:
        raise ValueError(
            f"speakers.json source_width={config.source_width}, but video width={actual_width}"
        )
    if config.source_height and config.source_height != actual_height:
        raise ValueError(
            f"speakers.json source_height={config.source_height}, but video height={actual_height}"
        )
    if config.crop_width <= 0 or config.crop_height <= 0:
        raise ValueError("crop_width and crop_height must be positive")
    if config.output_width <= 0 or config.output_height <= 0:
        raise ValueError("output_width and output_height must be positive")

    for speaker, box in config.speakers.items():
        if box.x < 0 or box.y < 0:
            raise ValueError(f"Speaker {speaker!r} has a negative crop coordinate")
        if box.x + config.crop_width > actual_width:
            raise ValueError(f"Speaker {speaker!r} crop extends beyond video width")
        if box.y + config.crop_height > actual_height:
            raise ValueError(f"Speaker {speaker!r} crop extends beyond video height")


def timeline_for_clip(
    clip: ClipRange,
    timeline: list[SpeakerSegment],
    default_speaker: str,
) -> list[SpeakerSegment]:
    relevant: list[SpeakerSegment] = []
    cursor = clip.start
    epsilon = 0.001

    for segment in timeline:
        if segment.end <= clip.start + epsilon:
            continue
        if segment.start >= clip.end - epsilon:
            break

        clipped_start = max(segment.start, clip.start)
        clipped_end = min(segment.end, clip.end)
        if clipped_start > cursor + epsilon:
            relevant.append(
                SpeakerSegment(start=cursor, end=clipped_start, speaker=default_speaker)
            )
        if clipped_end > clipped_start + epsilon:
            relevant.append(
                SpeakerSegment(
                    start=clipped_start,
                    end=clipped_end,
                    speaker=segment.speaker,
                )
            )
        cursor = max(cursor, clipped_end)

    if cursor < clip.end - epsilon:
        relevant.append(SpeakerSegment(start=cursor, end=clip.end, speaker=default_speaker))

    return merge_adjacent_segments(relevant)


def rotation_for_clip(
    clip: ClipRange,
    rotation: RotationConfig,
) -> list[SpeakerSegment]:
    rng = random.Random(rotation.seed + clip.number * 1009)
    cursor = clip.start
    segments: list[SpeakerSegment] = []
    use_primary = True

    while cursor < clip.end - 0.001:
        if use_primary:
            speaker = rotation.primary_speaker
            min_seconds = rotation.primary_min_seconds
            max_seconds = rotation.primary_max_seconds
        else:
            speaker = rotation.secondary_speaker
            min_seconds = rotation.secondary_min_seconds
            max_seconds = rotation.secondary_max_seconds

        span = min_seconds if min_seconds == max_seconds else rng.uniform(min_seconds, max_seconds)
        end = min(cursor + span, clip.end)
        segments.append(SpeakerSegment(start=cursor, end=end, speaker=speaker))
        cursor = end
        use_primary = not use_primary

    return merge_adjacent_segments(segments)


def merge_adjacent_segments(segments: list[SpeakerSegment]) -> list[SpeakerSegment]:
    merged: list[SpeakerSegment] = []
    epsilon = 0.001
    for segment in segments:
        if segment.end <= segment.start + epsilon:
            continue
        if merged and merged[-1].speaker == segment.speaker and abs(merged[-1].end - segment.start) <= epsilon:
            previous = merged.pop()
            merged.append(
                SpeakerSegment(
                    start=previous.start,
                    end=segment.end,
                    speaker=segment.speaker,
                )
            )
        else:
            merged.append(segment)
    return merged


def crop_filter(config: SpeakerConfig, speaker: str) -> str:
    box = config.speakers[speaker]
    return (
        f"crop={config.crop_width}:{config.crop_height}:{box.x}:{box.y},"
        f"scale={config.output_width}:{config.output_height}"
    )


def run_ffmpeg(command: list[str], dry_run: bool) -> None:
    if dry_run:
        print(" ".join(f'"{part}"' if " " in part else part for part in command))
        return
    subprocess.run(command, check=True)


def render_segment(
    source: Path,
    output: Path,
    segment: SpeakerSegment,
    config: SpeakerConfig,
    dry_run: bool,
) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        seconds_to_timestamp(segment.start),
        "-i",
        str(source),
        "-t",
        f"{duration_seconds(segment.start, segment.end):.3f}",
        "-vf",
        crop_filter(config, segment.speaker),
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
        str(output),
    ]
    run_ffmpeg(command, dry_run=dry_run)


def write_concat_file(path: Path, segment_paths: list[Path]) -> None:
    lines = []
    for segment_path in segment_paths:
        escaped = str(segment_path).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def concat_segments(
    concat_file: Path,
    output: Path,
    dry_run: bool,
) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(output),
    ]
    run_ffmpeg(command, dry_run=dry_run)


def render_clip(
    source: Path,
    clip: ClipRange,
    segments: list[SpeakerSegment],
    config: SpeakerConfig,
    output_dir: Path,
    temp_root: Path,
    dry_run: bool,
) -> Path:
    output = output_dir / f"clip_{clip.number:02d}.mp4"
    print(
        f"Clip {clip.number:02d}: {seconds_to_timestamp(clip.start)} - "
        f"{seconds_to_timestamp(clip.end)} -> {output}"
    )
    for segment in segments:
        print(
            f"  {seconds_to_timestamp(segment.start)} - "
            f"{seconds_to_timestamp(segment.end)}  {segment.speaker}"
        )

    if dry_run:
        return output

    clip_temp = temp_root / f"clip_{clip.number:02d}"
    clip_temp.mkdir(parents=True, exist_ok=True)
    segment_paths: list[Path] = []
    for index, segment in enumerate(segments, start=1):
        segment_path = clip_temp / f"segment_{index:03d}.mp4"
        render_segment(
            source=source,
            output=segment_path,
            segment=segment,
            config=config,
            dry_run=False,
        )
        segment_paths.append(segment_path)

    concat_file = clip_temp / "segments.txt"
    write_concat_file(concat_file, segment_paths)
    concat_segments(concat_file=concat_file, output=output, dry_run=False)
    return output


def render_clips(
    source: Path,
    clips: list[ClipRange],
    timeline: list[SpeakerSegment],
    config: SpeakerConfig,
    focus_mode: str,
    rotation: RotationConfig,
    output_dir: Path,
    dry_run: bool,
    keep_temp: bool,
) -> list[Path]:
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    rendered: list[Path] = []
    temp_context = tempfile.TemporaryDirectory(prefix="active_speaker_reframe_")
    temp_root = Path(temp_context.name)
    try:
        for clip in clips:
            if focus_mode == "timeline":
                segments = timeline_for_clip(
                    clip=clip,
                    timeline=timeline,
                    default_speaker=config.default_speaker,
                )
            else:
                segments = rotation_for_clip(clip=clip, rotation=rotation)
            rendered.append(
                render_clip(
                    source=source,
                    clip=clip,
                    segments=segments,
                    config=config,
                    output_dir=output_dir,
                    temp_root=temp_root,
                    dry_run=dry_run,
                )
            )

        if dry_run or keep_temp:
            if keep_temp and not dry_run:
                kept_root = output_dir / "_render_segments"
                if kept_root.exists():
                    shutil.rmtree(kept_root)
                shutil.copytree(temp_root, kept_root)
                print(f"Kept temporary segment files in {kept_root}")
        return rendered
    finally:
        temp_context.cleanup()


def selected_clips(clips: list[ClipRange], clip_number: int | None) -> list[ClipRange]:
    if clip_number is None:
        return clips
    selected = [clip for clip in clips if clip.number == clip_number]
    if not selected:
        raise ValueError(f"No clip {clip_number} found in durations file")
    return selected


def default_secondary_speaker(config: SpeakerConfig, primary_speaker: str) -> str:
    for speaker in config.speakers:
        if speaker != primary_speaker:
            return speaker
    raise ValueError("Rotation mode needs at least two speakers in speakers.json")


def resolve_rotation_config(args: argparse.Namespace, config: SpeakerConfig) -> RotationConfig:
    primary_speaker = args.primary_speaker or config.default_speaker
    if primary_speaker not in config.speakers:
        raise ValueError(f"Unknown primary speaker {primary_speaker!r}")

    secondary_speaker = args.secondary_speaker or default_secondary_speaker(
        config=config,
        primary_speaker=primary_speaker,
    )
    if secondary_speaker not in config.speakers:
        raise ValueError(f"Unknown secondary speaker {secondary_speaker!r}")
    if secondary_speaker == primary_speaker:
        raise ValueError("Primary and secondary speakers must be different")

    primary_min, primary_max = parse_seconds_range(args.primary_duration)
    secondary_min, secondary_max = parse_seconds_range(args.secondary_duration)
    return RotationConfig(
        primary_speaker=primary_speaker,
        secondary_speaker=secondary_speaker,
        primary_min_seconds=primary_min,
        primary_max_seconds=primary_max,
        secondary_min_seconds=secondary_min,
        secondary_max_seconds=secondary_max,
        seed=args.rotation_seed,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render 9:16 clips that rotate or hard-switch crop focus."
    )
    parser.add_argument("--durations", type=Path, default=DEFAULT_DURATIONS)
    parser.add_argument("--video", type=Path, help="Specific source video path.")
    parser.add_argument("--video-dir", type=Path, default=DEFAULT_VIDEO_DIR)
    parser.add_argument("--timeline", type=Path, default=DEFAULT_TIMELINE)
    parser.add_argument("--speakers", type=Path, default=DEFAULT_SPEAKERS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--clip", type=int, help="Render only one clip number.")
    parser.add_argument(
        "--focus-mode",
        choices=("rotate", "timeline"),
        default="rotate",
        help="rotate alternates crops by duration; timeline uses speaker_timeline.csv.",
    )
    parser.add_argument(
        "--primary-speaker",
        help="Speaker crop shown first in rotate mode. Defaults to default_speaker.",
    )
    parser.add_argument(
        "--secondary-speaker",
        help="Speaker crop shown second in rotate mode. Defaults to the other speaker.",
    )
    parser.add_argument(
        "--primary-duration",
        default="3-4",
        help='Seconds or range for the first speaker in rotate mode, e.g. "3.5" or "3-4".',
    )
    parser.add_argument(
        "--secondary-duration",
        default="2-3",
        help='Seconds or range for the second speaker in rotate mode, e.g. "2.5" or "2-3".',
    )
    parser.add_argument(
        "--rotation-seed",
        type=int,
        default=7,
        help="Seed for repeatable dynamic rotation durations.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print render plan only.")
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep intermediate rendered segments beside the final clips.",
    )
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg was not found on PATH.")
    if not shutil.which("ffprobe"):
        raise SystemExit("ffprobe was not found on PATH.")

    clips = selected_clips(parse_clip_durations(args.durations), args.clip)
    source = args.video if args.video else find_source_video(args.video_dir)
    config = load_speaker_config(args.speakers)
    actual_width, actual_height = probe_video(source)
    validate_config(config, actual_width=actual_width, actual_height=actual_height)
    timeline = load_timeline(args.timeline, known_speakers=set(config.speakers))
    rotation = resolve_rotation_config(args, config)

    outputs = render_clips(
        source=source,
        clips=clips,
        timeline=timeline,
        config=config,
        focus_mode=args.focus_mode,
        rotation=rotation,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        keep_temp=args.keep_temp,
    )

    print("Done.")
    for output in outputs:
        print(output)


if __name__ == "__main__":
    main()
