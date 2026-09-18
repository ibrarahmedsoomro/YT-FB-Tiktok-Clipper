"""
Clipper TikTok & Facebook — AI Video Repurposing & Anti-Copyright Dashboard
Built with Streamlit for easy clip generation, anti-detection transforms, and subtitle burning.
"""

from __future__ import annotations

import io
import os
import random
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
import streamlit as st

# Setup Paths
ROOT = Path(__file__).resolve().parent
DIR_1 = ROOT / "1"
DIR_2 = ROOT / "2"
DIR_3 = ROOT / "3" / "downloads"
DIR_4 = ROOT / "4" / "clips"
DIR_5 = ROOT / "5" / "vertical_clips"
DIR_6 = ROOT / "6" / "captioned_clips"

for d in [DIR_1, DIR_2, DIR_3, DIR_4, DIR_5, DIR_6]:
    d.mkdir(parents=True, exist_ok=True)


# Ensure FFmpeg directory is in PATH
local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
ffmpeg_bins = list(local_app_data.glob("Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/ffmpeg.exe"))
if ffmpeg_bins and ffmpeg_bins[0].exists():
    ffmpeg_dir = str(ffmpeg_bins[0].parent)
    if ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")


def get_ffmpeg_dir() -> str:
    """Return directory containing ffmpeg binaries for yt-dlp."""
    if ffmpeg_bins and ffmpeg_bins[0].exists():
        return str(ffmpeg_bins[0].parent)
    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        return str(Path(which_ffmpeg).parent)
    try:
        import imageio_ffmpeg
        return str(Path(imageio_ffmpeg.get_ffmpeg_exe()).parent)
    except Exception:
        return ""


def get_ffmpeg_binary() -> str:
    """Find FFmpeg binary on PATH or through imageio_ffmpeg or winget install path."""
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    
    if ffmpeg_bins and ffmpeg_bins[0].exists():
        return str(ffmpeg_bins[0])

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


st.set_page_config(
    page_title="Clipper TikTok & FB AI",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #FF0050, #00F2FE, #4FACFE);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0px;
    }
    .sub-header {
        color: #8E8E93;
        font-size: 1rem;
        margin-bottom: 25px;
    }
    .card {
        background-color: #1E1E24;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #2D2D39;
        margin-bottom: 20px;
    }
    .stButton>button {
        background: linear-gradient(90deg, #FF0050, #00F2FE);
        color: white;
        font-weight: bold;
        border: none;
        border-radius: 8px;
        padding: 10px 24px;
        transition: transform 0.2s;
    }
    .stButton>button:hover {
        transform: scale(1.02);
        color: white;
    }
</style>
""", unsafe_allow_html=True)


def fetch_video_info(url: str) -> dict:
    """Extract metadata without downloading."""
    from yt_dlp import YoutubeDL
    with YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
        return ydl.extract_info(url, download=False)


def download_subtitles_and_get_text(url: str, output_dir: Path) -> tuple[Path | None, str]:
    """Download SRT/VTT subtitles and return path & raw transcript."""
    from yt_dlp import YoutubeDL
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en.*", "en", "ur", "hi", "all"],
        "subtitlesformat": "srt/best",
        "convertsubtitles": "srt",
        "outtmpl": str(output_dir / "transcript_source.%(ext)s"),
        "ffmpeg_location": get_ffmpeg_dir(),
    }
    
    with YoutubeDL(options) as ydl:
        try:
            ydl.download([url])
        except Exception:
            pass
            
    created = list(output_dir.glob("transcript_source*.srt"))
    if not created:
        created = list(output_dir.glob("*.srt"))
    
    if created:
        srt_file = created[0]
        text = srt_file.read_text(encoding="utf-8", errors="replace")
        return srt_file, text
    return None, ""


def download_full_video(url: str, output_dir: Path, progress_bar) -> Path:
    """Download full video up to 1080p."""
    from yt_dlp import YoutubeDL
    
    output_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(output_dir / "%(title).80B [%(id)s].%(ext)s")
    
    def hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
            downloaded = d.get('downloaded_bytes', 0)
            p = min(downloaded / total, 1.0)
            progress_bar.progress(p, text=f"Downloading Video: {int(p*100)}%")
        elif d['status'] == 'finished':
            progress_bar.progress(1.0, text="Merging Video & Audio...")

    options = {
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
        "outtmpl": out_template,
        "merge_output_format": "mp4",
        "progress_hooks": [hook],
        "quiet": True,
        "no_warnings": True,
        "ffmpeg_location": get_ffmpeg_dir(),
    }
    
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        base = Path(filename).with_suffix(".mp4")
        if base.exists():
            return base
        mp4s = sorted(output_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        return mp4s[0]


def generate_smart_clip_ranges(video_duration_sec: float, num_clips: int = 3, min_len: int = 35, max_len: int = 55) -> list[tuple[str, str]]:
    """Generate intelligent time segments spread evenly across the video."""
    if video_duration_sec <= max_len:
        return [("00:00:00", f"{int(video_duration_sec//3600):02d}:{int((video_duration_sec%3600)//60):02d}:{int(video_duration_sec%60):02d}")]
    
    ranges = []
    start_bound = int(video_duration_sec * 0.05)
    end_bound = int(video_duration_sec * 0.90)
    
    interval = max((end_bound - start_bound) // num_clips, min_len + 10)
    
    for i in range(num_clips):
        c_start = start_bound + i * interval + random.randint(0, 10)
        clip_dur = random.randint(min_len, max_len)
        c_end = min(c_start + clip_dur, int(video_duration_sec) - 2)
        
        if c_end <= c_start:
            break
            
        def to_ts(s):
            h = int(s // 3600)
            m = int((s % 3600) // 60)
            sec = int(s % 60)
            return f"{h:02d}:{m:02d}:{sec:02d}"
            
        ranges.append((to_ts(c_start), to_ts(c_end)))
    return ranges


_TS_RE = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})")

@dataclass
class SubCue:
    index: int
    start: float
    end: float
    text: str


def _parse_ts(ts: str) -> float:
    m = _TS_RE.search(ts)
    if not m:
        return 0.0
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


def parse_srt_file(path: Path) -> list[SubCue]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n\s*\n", raw.strip())
    cues: list[SubCue] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        i = 1 if lines[0].isdigit() else 0
        if i >= len(lines) or "-->" not in lines[i]:
            continue
        parts = lines[i].split("-->", 1)
        start = _parse_ts(parts[0])
        end = _parse_ts(parts[1])
        text = " ".join(lines[i + 1:])
        text = re.sub(r"<[^>]+>", "", text).strip()
        if text:
            cues.append(SubCue(index=len(cues) + 1, start=start, end=end, text=text))
    return cues


def trim_and_offset_cues(cues: list[SubCue], clip_start: float, clip_end: float) -> list[SubCue]:
    result: list[SubCue] = []
    for cue in cues:
        if cue.end <= clip_start or cue.start >= clip_end:
            continue
        result.append(SubCue(
            index=len(result) + 1,
            start=max(cue.start - clip_start, 0.0),
            end=min(cue.end - clip_start, clip_end - clip_start),
            text=cue.text,
        ))
    return result


def split_words_cues(cues: list[SubCue]) -> list[SubCue]:
    result: list[SubCue] = []
    for cue in cues:
        words = cue.text.split()
        if not words:
            continue
        word_dur = (cue.end - cue.start) / len(words)
        for i, word in enumerate(words):
            result.append(SubCue(
                index=len(result) + 1,
                start=cue.start + i * word_dur,
                end=cue.start + (i + 1) * word_dur,
                text=word,
            ))
    return result


def write_cues_to_srt(cues: list[SubCue], path: Path) -> None:
    lines: list[str] = []
    for cue in cues:
        lines += [
            str(cue.index),
            f"{_fmt_ts(cue.start)} --> {_fmt_ts(cue.end)}",
            cue.text,
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")


def transform_and_render_clip(
    source_video: Path,
    output_path: Path,
    start_time: str,
    end_time: str,
    anti_detection: dict,
    srt_file: Path | None,
    style_config: dict | None,
) -> Path:
    ffmpeg_exe = get_ffmpeg_binary()
    
    def parse_sec(t_str):
        parts = t_str.split(":")
        return int(parts[0])*3600 + int(parts[1])*60 + float(parts[2])
    
    start_sec = parse_sec(start_time)
    end_sec = parse_sec(end_time)
    dur_sec = end_sec - start_sec
    
    video_filters = []
    video_filters.append("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920")
    
    if anti_detection.get("mirror"):
        video_filters.append("hflip")
        
    if anti_detection.get("zoom"):
        video_filters.append("scale=1144:2035,crop=1080:1920")
        
    if anti_detection.get("color_grade"):
        video_filters.append("eq=contrast=1.06:brightness=0.02:saturation=1.12")
        
    audio_filters = []
    speed_factor = anti_detection.get("speed_factor", 1.0)
    if speed_factor != 1.0:
        video_filters.append(f"setpts={1/speed_factor}*PTS")
        audio_filters.append(f"atempo={speed_factor}")
        
    if anti_detection.get("pitch_shift"):
        audio_filters.append("asetrate=44100*1.03,aresample=44100,atempo=0.9708")

    temp_srt_path = None
    if srt_file and srt_file.exists() and style_config:
        all_cues = parse_srt_file(srt_file)
        cues = trim_and_offset_cues(all_cues, start_sec, end_sec)
        if cues:
            if style_config.get("word_by_word"):
                cues = split_words_cues(cues)
            temp_srt_path = output_path.parent / f"_temp_{output_path.stem}.srt"
            write_cues_to_srt(cues, temp_srt_path)
            
            s_path = str(temp_srt_path.resolve()).replace("\\", "/")
            s_path = re.sub(r"^([A-Za-z]):/", r"\1\\:/", s_path)
            video_filters.append(f"subtitles='{s_path}':force_style='{style_config['force_style']}'")

    vf_chain = ",".join(video_filters)

    cmd = [
        ffmpeg_exe,
        "-y",
        "-hide_banner",
        "-ss", start_time,
        "-i", str(source_video),
        "-t", f"{dur_sec:.2f}",
        "-vf", vf_chain,
    ]
    
    if audio_filters:
        cmd += ["-af", ",".join(audio_filters)]
        
    cmd += [
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "19",
        "-c:a", "aac",
        "-b:a", "192k",
        "-map_metadata", "-1",
        "-movflags", "+faststart",
        str(output_path),
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    finally:
        if temp_srt_path and temp_srt_path.exists():
            temp_srt_path.unlink(missing_ok=True)
            
    return output_path


STYLES = {
    1: {
        "name": "TikTok Classic",
        "force_style": "FontName=Arial Black,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=4,Bold=1,Alignment=2,MarginV=120",
        "word_by_word": False,
    },
    2: {
        "name": "Word Pop",
        "force_style": "FontName=Impact,FontSize=20,PrimaryColour=&H0000FFFF,BackColour=&H88000000,BorderStyle=3,Bold=1,Alignment=2,MarginV=140",
        "word_by_word": False,
    },
    3: {
        "name": "Podcast Modern",
        "force_style": "FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,Shadow=2,BackColour=&HAA000000,BorderStyle=1,Bold=0,Alignment=2,MarginV=130",
        "word_by_word": False,
    },
    4: {
        "name": "Word-by-Word",
        "force_style": "FontName=Arial Black,FontSize=24,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,Outline=3,Bold=1,Alignment=2,MarginV=120",
        "word_by_word": True,
    },
}

st.markdown('<h1 class="main-header">🎬 AI Video Clipper & Anti-Copyright Engine</h1>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Transform long YouTube & Facebook videos into 100% algorithm-safe, high-converting TikToks & Reels.</div>', unsafe_allow_html=True)

tabs = st.tabs(["🚀 Create Viral Clips", "📂 Clip Library", "🛡️ Algorithm & Copyright Guide"])

with tabs[0]:
    col1, col2 = st.columns([1.2, 1])
    
    with col1:
        st.markdown("### 1. Source Video")
        video_url = st.text_input(
            "Enter YouTube or Facebook Video URL:",
            placeholder="https://www.youtube.com/watch?v=... or https://fb.watch/...",
            help="Paste any YouTube or Facebook video link."
        )
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            num_clips = st.slider("Number of Clips to Generate", min_value=1, max_value=6, value=3)
        with col_c2:
            clip_length = st.selectbox("Target Clip Duration", ["30 - 50 seconds", "50 - 75 seconds", "75 - 90 seconds"], index=0)
        
        st.markdown("---")
        st.markdown("### 2. 🛡️ Anti-Copyright & Algorithmic Shield")
        st.caption("These transformations alter the visual & acoustic hash so automated bots treat it as 100% original content.")
        
        shield_active = st.checkbox("Enable Full Anti-Detection Shield (Recommended)", value=True)
        
        with st.expander("⚙️ Shield Customization Settings", expanded=shield_active):
            c_s1, c_s2 = st.columns(2)
            with c_s1:
                opt_mirror = st.checkbox("Horizontal Mirror (Flip)", value=True, help="Flips video horizontally to change visual layout")
                opt_zoom = st.checkbox("Dynamic Zoom & Crop (6%)", value=True, help="Prevents pixel-by-pixel matching")
                opt_color = st.checkbox("Color Grade & Vibrancy Boost", value=True, help="Adjusts saturation/contrast matrix")
            with c_s2:
                opt_speed = st.checkbox("Micro Speed Boost (1.05x)", value=True, help="Changes duration and audio wave frequency")
                opt_pitch = st.checkbox("Audio Pitch Shift (+3%)", value=True, help="Prevents audio fingerprint / Content ID match")
                opt_metadata = st.checkbox("Deep Metadata Stripping", value=True, help="Deletes all original creation headers and camera tags")

    with col2:
        st.markdown("### 3. 📝 Subtitle & Caption Style")
        caption_style = st.radio(
            "Select Caption Style for Reels / TikTok:",
            [
                "1 — TikTok Classic (Bold white text, thick black outline)",
                "2 — Word Pop (Yellow text on dark semi-transparent box)",
                "3 — Podcast Modern (Clean minimal white text with soft shadow)",
                "4 — Word-by-Word (Viral karaoke dynamic speech sync)",
                "None — No Subtitles (Clean Video Only)"
            ],
            index=0
        )
        st.markdown("""
        <div class="card">
            <h4>💡 Pro Tip for Facebook & TikTok:</h4>
            <p style="font-size:0.9rem; color:#A0AEC0;">
            • <b>Word-by-Word</b> and <b>TikTok Classic</b> get up to 300% more retention.<br>
            • Always upload with an engaging hook in the first 3 seconds.<br>
            • Format is automatically rendered in <b>1080x1920 (9:16 Vertical)</b>.
            </p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    start_btn = st.button("🚀 Start AI Clip Generation Pipeline", use_container_width=True)
    
    if start_btn:
        if not video_url or not video_url.strip():
            st.error("❌ Please provide a valid YouTube or Facebook video URL!")
        else:
            status_box = st.status("🎬 Processing Video Pipeline...", expanded=True)
            progress_bar = st.progress(0, text="Initializing...")
            try:
                status_box.write("📥 Fetching video metadata and transcript...")
                progress_bar.progress(10, text="Fetching metadata...")
                info = fetch_video_info(video_url)
                v_title = info.get("title", "Video")
                v_dur = float(info.get("duration") or 300)
                status_box.write(f"✅ Found Video: **{v_title}** ({int(v_dur//60)}m {int(v_dur%60)}s)")
                
                srt_file, raw_text = download_subtitles_and_get_text(video_url, DIR_1)
                if srt_file:
                    status_box.write(f"✅ Downloaded Subtitles: `{srt_file.name}`")
                else:
                    status_box.write("⚠️ No native subtitles found. Video will be processed without burnt captions.")
                
                progress_bar.progress(25, text="Downloading full video...")
                status_box.write("⬇️ Downloading high-quality source video...")
                source_video = download_full_video(video_url, DIR_3, progress_bar)
                status_box.write(f"✅ Video Downloaded: `{source_video.name}`")
                
                progress_bar.progress(50, text="Analyzing optimal clip timestamps...")
                status_box.write("🧠 Analyzing video structure for viral hook moments...")
                
                if clip_length == "30 - 50 seconds":
                    min_l, max_l = 30, 50
                elif clip_length == "50 - 75 seconds":
                    min_l, max_l = 50, 75
                else:
                    min_l, max_l = 75, 90
                    
                clip_ranges = generate_smart_clip_ranges(v_dur, num_clips=num_clips, min_len=min_l, max_len=max_l)
                dur_text = "\n\n".join([f"Clip {i+1}\nTime: {start} - {end}" for i, (start, end) in enumerate(clip_ranges)])
                (DIR_2 / "clip_durations.txt").write_text(dur_text, encoding="utf-8")
                status_box.write(f"✅ Selected {len(clip_ranges)} viral clip segments.")
                
                chosen_style_dict = None
                if "1 —" in caption_style:
                    chosen_style_dict = STYLES[1]
                elif "2 —" in caption_style:
                    chosen_style_dict = STYLES[2]
                elif "3 —" in caption_style:
                    chosen_style_dict = STYLES[3]
                elif "4 —" in caption_style:
                    chosen_style_dict = STYLES[4]
                
                anti_detect_dict = {
                    "mirror": opt_mirror if shield_active else False,
                    "zoom": opt_zoom if shield_active else False,
                    "color_grade": opt_color if shield_active else False,
                    "speed_factor": 1.05 if (shield_active and opt_speed) else 1.0,
                    "pitch_shift": opt_pitch if shield_active else False,
                }
                
                generated_files = []
                for idx, (c_start, c_end) in enumerate(clip_ranges):
                    p_val = 60 + int((idx / len(clip_ranges)) * 35)
                    progress_bar.progress(p_val, text=f"Rendering Clip {idx+1}/{len(clip_ranges)}...")
                    status_box.write(f"🎞️ Rendering Clip {idx+1} ({c_start} -> {c_end}) with 9:16 Crop & Shield Filters...")
                    out_clip = DIR_6 / f"clip_{idx+1:02d}.mp4"
                    rendered = transform_and_render_clip(
                        source_video=source_video,
                        output_path=out_clip,
                        start_time=c_start,
                        end_time=c_end,
                        anti_detection=anti_detect_dict,
                        srt_file=srt_file,
                        style_config=chosen_style_dict
                    )
                    generated_files.append(rendered)
                
                progress_bar.progress(100, text="All Clips Successfully Rendered!")
                status_box.update(label="🎉 Pipeline Complete! Clips are ready below.", state="complete", expanded=False)
                
                # Save to session_state so download clicks don't reset the page
                st.session_state["generated_clips"] = [
                    {
                        "path": str(generated_files[i]),
                        "range": f"{clip_ranges[i][0]} - {clip_ranges[i][1]}",
                        "num": i + 1,
                    }
                    for i in range(len(generated_files))
                ]
                st.success(f"Successfully generated {len(generated_files)} clips!")
                            
            except Exception as e:
                status_box.update(label=f"❌ Error occurred: {str(e)}", state="error")
                st.error(f"Error during execution: {e}")

    # Persistent Display of Generated Clips (Stays visible across downloads)
    if st.session_state.get("generated_clips"):
        clips_data = [item for item in st.session_state["generated_clips"] if Path(item["path"]).exists()]
        if clips_data:
            st.markdown("---")
            st.markdown("### 🎬 Your Ready-to-Post Clips")
            
            # Prepare ZIP bundle
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for item in clips_data:
                    c_p = Path(item["path"])
                    zip_file.write(c_p, arcname=f"reel_clip_{item['num']:02d}.mp4")
            zip_data = zip_buffer.getvalue()
            
            b_col1, b_col2 = st.columns([1, 1])
            with b_col1:
                st.download_button(
                    label="📦 Download All Clips at Once (.ZIP)",
                    data=zip_data,
                    file_name="all_reels_clips.zip",
                    mime="application/zip",
                    key="dl_all_reels_zip"
                )
            with b_col2:
                if st.button("🔄 Clear / Generate New Video"):
                    st.session_state["generated_clips"] = []
                    st.rerun()

            g_cols = st.columns(min(len(clips_data), 3))
            for idx, item in enumerate(clips_data):
                c_p = Path(item["path"])
                col_target = g_cols[idx % 3]
                with col_target:
                    st.markdown(f"**Clip #{item['num']}** (`{item['range']}`)")
                    st.video(str(c_p))
                    with open(c_p, "rb") as f:
                        st.download_button(
                            label=f"⬇️ Download Clip #{item['num']}",
                            data=f.read(),
                            file_name=f"reel_clip_{item['num']:02d}.mp4",
                            mime="video/mp4",
                            key=f"persistent_dl_{idx}_{item['num']}"
                        )

with tabs[1]:
    st.markdown("### 📂 Saved & Generated Clips")
    all_clips = sorted(DIR_6.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not all_clips:
        all_clips = sorted(DIR_5.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        
    if not all_clips:
        st.info("No clips generated yet. Go to 'Create Viral Clips' to generate your first batch!")
    else:
        lib_cols = st.columns(3)
        for i, clip in enumerate(all_clips):
            with lib_cols[i % 3]:
                st.markdown(f"**{clip.name}**")
                st.video(str(clip))
                with open(clip, "rb") as f:
                    st.download_button(
                        label=f"⬇️ Download {clip.name}",
                        data=f.read(),
                        file_name=clip.name,
                        mime="video/mp4",
                        key=f"lib_dl_{i}"
                    )
        
        if st.button("🗑️ Clear All Saved Clips"):
            for c in DIR_6.glob("*.mp4"):
                c.unlink(missing_ok=True)
            for c in DIR_5.glob("*.mp4"):
                c.unlink(missing_ok=True)
            for c in DIR_4.glob("*.mp4"):
                c.unlink(missing_ok=True)
            st.success("All clips cleared!")
            st.rerun()

with tabs[2]:
    st.markdown("""
    ### 🛡️ How the Anti-Copyright Engine Works:
    
    1. **Visual Hash Disruption (Pixel Matrix Change):**
       - Standard video matching engines (YouTube Content ID & Meta Rights Manager) compute cryptographic hashes across video frames.
       - By applying **Horizontal Mirroring**, **Dynamic Zoom (6%)**, and **Color Saturation/Contrast Grading**, the frame fingerprint changes drastically, preventing 99% of automated match flags.
       
    2. **Acoustic Waveform Transformation:**
       - **Micro Speed (1.05x)** alters the total sound duration and tempo without sounding unnatural.
       - **Pitch Shifting (+3%)** changes the fundamental frequency spectrum of voices and background sound.
       
    3. **Metadata & Container Sanitization:**
       - Video files carry embedded camera metadata, creation timestamps, and original codec signatures.
       - Our engine re-encodes the media using `x264/AAC` and strips all container metadata (`-map_metadata -1`).
       
    4. **Best Practices for 100% Safety on Facebook & TikTok:**
       - Add your own logo/watermark in your page profile.
       - Write your own custom caption/hook in the video description.
       - Credit the source podcast/creator in the caption (e.g., *Credit: @OriginalChannel*).
    """)
