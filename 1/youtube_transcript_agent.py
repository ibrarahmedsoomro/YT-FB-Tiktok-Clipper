"""
Agent helper for retrieving clean YouTube transcripts with yt-dlp.

Behavior:
- Treat a pasted YouTube URL as a request for that video's transcript.
- Check available creator/manual subtitles and auto-generated captions.
- Prefer creator/manual English subtitles when available.
- Fall back to YouTube auto-generated English captions.
- Download subtitles only, never the video.
- Convert subtitle timestamps into clean paragraph text.

Command examples:
    python youtube_transcript_agent.py "https://www.youtube.com/watch?v=VIDEO_ID"
    python youtube_transcript_agent.py "YOUTUBE_URL" --save transcript.txt
    python youtube_transcript_agent.py "YOUTUBE_URL" --keep-subtitle-file
"""

from __future__ import annotations

import argparse
import html
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


YOUTUBE_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com|youtu\.be|m\.youtube\.com|music\.youtube\.com)/\S+",
    re.IGNORECASE,
)

TIMESTAMP_RE = re.compile(
    r"^\d{1,2}:\d{2}(?::\d{2})?[,.]\d{3}\s+-->\s+\d{1,2}:\d{2}(?::\d{2})?[,.]\d{3}"
)

TAG_RE = re.compile(r"<[^>]+>")
VTT_METADATA_RE = re.compile(r"^(WEBVTT|Kind:|Language:|NOTE\b|STYLE\b|REGION\b)")


@dataclass(frozen=True)
class SubtitleChoice:
    source: str
    language: str
    extension: str | None


def _youtube_dl_class():
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:  # pragma: no cover - friendly runtime failure.
        raise SystemExit(
            "Missing dependency: yt-dlp. Install it with `python -m pip install yt-dlp`."
        ) from exc
    return YoutubeDL


def contains_youtube_url(text: str) -> bool:
    """Return True when user text contains a YouTube video-like URL."""
    return bool(YOUTUBE_URL_RE.search(text))


def extract_youtube_url(text: str) -> str:
    """Extract the first YouTube URL from arbitrary user text."""
    match = YOUTUBE_URL_RE.search(text)
    if not match:
        raise ValueError("No YouTube URL found in the supplied text.")
    return match.group(0).rstrip(").,;]")


def _ydl_quiet_options() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }


def inspect_subtitles(url: str) -> dict:
    """Use yt-dlp's metadata extraction, equivalent in spirit to --list-subs."""
    YoutubeDL = _youtube_dl_class()
    with YoutubeDL(_ydl_quiet_options()) as ydl:
        info = ydl.extract_info(url, download=False)

    return {
        "title": info.get("title"),
        "id": info.get("id"),
        "manual": sorted((info.get("subtitles") or {}).keys()),
        "automatic": sorted((info.get("automatic_captions") or {}).keys()),
        "_raw": info,
    }


def _language_matches(language: str, requested_patterns: Iterable[str]) -> bool:
    language_lower = language.lower()
    for pattern in requested_patterns:
        pattern_lower = pattern.lower()
        if pattern_lower.endswith(".*"):
            if language_lower.startswith(pattern_lower[:-2]):
                return True
        elif language_lower == pattern_lower or language_lower.startswith(pattern_lower + "-"):
            return True
    return False


def choose_subtitle(
    info: dict,
    languages: Iterable[str] = ("en.*", "en"),
    prefer_manual: bool = True,
) -> SubtitleChoice:
    """Choose the best subtitle track, preferring manual subtitles over auto captions."""
    source_order = ("manual", "automatic") if prefer_manual else ("automatic", "manual")
    source_map = {
        "manual": info.get("subtitles") or {},
        "automatic": info.get("automatic_captions") or {},
    }

    for source in source_order:
        tracks = source_map[source]
        for language in tracks:
            if _language_matches(language, languages):
                extension = None
                for track in tracks[language]:
                    if track.get("ext") in {"srt", "vtt", "json3", "srv3", "ttml"}:
                        extension = track.get("ext")
                        break
                return SubtitleChoice(source=source, language=language, extension=extension)

    raise RuntimeError(
        "No matching subtitles found. Try another language, or run "
        '`yt-dlp --list-subs "YOUTUBE_URL"` to inspect available tracks.'
    )


def download_subtitle_file(
    url: str,
    output_dir: Path,
    languages: Iterable[str] = ("en.*",),
) -> Path:
    """
    Download subtitles only, using yt-dlp options equivalent to:

    yt-dlp --skip-download --write-subs --write-auto-subs
           --sub-langs "en.*" --convert-subs srt "YOUTUBE_URL"
    """
    YoutubeDL = _youtube_dl_class()
    output_dir.mkdir(parents=True, exist_ok=True)
    before = set(output_dir.glob("*"))

    options = {
        **_ydl_quiet_options(),
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": list(languages),
        "subtitlesformat": "srt/vtt/best",
        "convertsubtitles": "srt",
        "outtmpl": str(output_dir / "%(title).120B [%(id)s].%(ext)s"),
    }

    with YoutubeDL(options) as ydl:
        ydl.download([url])

    created = [path for path in output_dir.glob("*") if path not in before]
    subtitle_files = [
        path
        for path in created
        if path.suffix.lower() in {".srt", ".vtt", ".json3", ".srv3", ".ttml"}
    ]

    if not subtitle_files:
        raise RuntimeError("yt-dlp completed, but no subtitle file was created.")

    subtitle_files.sort(key=lambda path: (path.suffix.lower() != ".srt", path.name.lower()))
    return subtitle_files[0]


def _parse_json3(text: str) -> str:
    data = json.loads(text)
    pieces: list[str] = []
    for event in data.get("events", []):
        segment_text = "".join(seg.get("utf8", "") for seg in event.get("segs", []))
        cleaned = " ".join(segment_text.split())
        if cleaned:
            pieces.append(cleaned)
    return _dedupe_joined_lines(pieces)


def _dedupe_joined_lines(lines: Iterable[str]) -> str:
    cleaned_lines: list[str] = []
    previous = None

    for line in lines:
        line = html.unescape(TAG_RE.sub("", line)).strip()
        line = re.sub(r"\s+", " ", line)
        if not line or line == previous:
            continue
        cleaned_lines.append(line)
        previous = line

    text = " ".join(cleaned_lines)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def subtitle_file_to_transcript(path: Path) -> str:
    """Convert an SRT/VTT/JSON subtitle file into a clean paragraph transcript."""
    text = path.read_text(encoding="utf-8", errors="replace")

    if path.suffix.lower() == ".json3":
        return _parse_json3(text)

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line:
            continue
        if line.isdigit():
            continue
        if TIMESTAMP_RE.match(line):
            continue
        if VTT_METADATA_RE.match(line):
            continue
        if line.startswith(("{", "}")):
            continue

        line = re.sub(r"^\d{1,2}:\d{2}(?::\d{2})?[,.]\d{3}\s*", "", line)
        lines.append(line)

    transcript = _dedupe_joined_lines(lines)
    if not transcript:
        raise RuntimeError(f"No transcript text could be extracted from {path}.")
    return transcript


def get_youtube_transcript(
    user_text_or_url: str,
    languages: Iterable[str] = ("en.*",),
    keep_subtitle_file: bool = False,
    output_dir: Path | None = None,
) -> str:
    """Main agent entry point: pass user text or a URL and get clean transcript text."""
    url = extract_youtube_url(user_text_or_url)
    inspected = inspect_subtitles(url)
    choose_subtitle(inspected["_raw"], languages=languages, prefer_manual=True)

    if output_dir is None:
        with tempfile.TemporaryDirectory(prefix="yt_transcript_") as temp_dir:
            subtitle_file = download_subtitle_file(url, Path(temp_dir), languages=languages)
            return subtitle_file_to_transcript(subtitle_file)

    subtitle_file = download_subtitle_file(url, output_dir, languages=languages)
    transcript = subtitle_file_to_transcript(subtitle_file)
    if not keep_subtitle_file:
        subtitle_file.unlink(missing_ok=True)
    return transcript


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch a clean YouTube transcript using yt-dlp subtitles/captions."
    )
    parser.add_argument("text_or_url", help="A YouTube URL, or text containing one.")
    parser.add_argument("--lang", default="en.*", help='Subtitle language pattern, e.g. "en.*" or "es".')
    parser.add_argument("--save", type=Path, help="Optional path to save the clean transcript.")
    parser.add_argument(
        "--keep-subtitle-file",
        action="store_true",
        help="Keep the downloaded subtitle file beside the saved transcript or in ./subtitles.",
    )
    parser.add_argument(
        "--subtitle-dir",
        type=Path,
        default=Path("subtitles"),
        help="Directory used when keeping subtitle files.",
    )
    args = parser.parse_args()

    output_dir = args.subtitle_dir if args.keep_subtitle_file else None
    transcript = get_youtube_transcript(
        args.text_or_url,
        languages=(args.lang,),
        keep_subtitle_file=args.keep_subtitle_file,
        output_dir=output_dir,
    )

    if args.save:
        args.save.write_text(transcript + "\n", encoding="utf-8")
        print(f"Saved transcript to {args.save}")
    else:
        print(transcript)


if __name__ == "__main__":
    main()
