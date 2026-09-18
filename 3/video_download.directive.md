# Video Download Directive

Purpose: download the source YouTube video for the clipping workflow.

Input:

- The agent receives the same YouTube URL used by folder `1`.
- Folder `2` provides clip durations, but folder `3` only downloads the full source video.

Agent behavior:

1. Use `yt-dlp` to download the video.
2. Prefer the best available quality up to `1080p`.
3. If `1080p` is unavailable, fall back to `720p`.
4. Download video and audio together when available, or merge best video plus best audio.
5. Save the final downloaded video as an `.mp4` file inside `3/downloads`.
6. Do not download subtitles in this step.
7. Do not clip the video in this step.

Best practical command:

```bash
yt-dlp -f "bv*[height<=1080]+ba/b[height<=1080]/bv*[height<=720]+ba/b[height<=720]" --merge-output-format mp4 -o "3/downloads/%(title).120B [%(id)s].%(ext)s" "YOUTUBE_URL"
```

If the command fails because the highest-quality stream is unavailable, retry with a stricter 720p command:

```bash
yt-dlp -f "bv*[height<=720]+ba/b[height<=720]" --merge-output-format mp4 -o "3/downloads/%(title).120B [%(id)s].%(ext)s" "YOUTUBE_URL"
```

Expected output:

- A downloaded `.mp4` video file in `3/downloads`.
- This file will be used later with folder `2` clip durations to create final clips.
