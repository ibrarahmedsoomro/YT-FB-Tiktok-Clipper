# YouTube Transcript Directive

When the user pastes a YouTube video link, interpret it as a request for the transcript of that video.

Use `youtube_transcript_agent.py` as the agent helper.

Required behavior:

1. Detect a YouTube URL in the user's message.
2. Check available subtitles first, equivalent to:

   ```bash
   yt-dlp --list-subs "YOUTUBE_URL"
   ```

3. Download subtitles only, never the video.
4. Prefer creator/manual subtitles:

   ```bash
   yt-dlp --skip-download --write-subs --sub-langs en --sub-format srt "YOUTUBE_URL"
   ```

5. If manual subtitles are unavailable, use YouTube auto-generated captions:

   ```bash
   yt-dlp --skip-download --write-auto-subs --sub-langs en --sub-format srt "YOUTUBE_URL"
   ```

6. Best default behavior is to request both manual and automatic captions:

   ```bash
   yt-dlp --skip-download --write-subs --write-auto-subs --sub-langs "en.*" --convert-subs srt "YOUTUBE_URL"
   ```

7. Convert the downloaded subtitle file into a clean transcript by removing cue numbers, timestamps, WebVTT metadata, markup, duplicate caption fragments, and extra whitespace.
8. Return the clean paragraph transcript to the user.

Notes:

- `--write-subs` gets creator/manual subtitles.
- `--write-auto-subs` gets YouTube auto-generated captions.
- `--skip-download` prevents video download and keeps the operation subtitle-only.
- `--list-subs`, `--sub-langs`, and `--sub-format` should be used when choosing the right subtitle track.
- `--convert-subs srt` can convert subtitles to SRT format. yt-dlp supports subtitle conversion to `ass`, `lrc`, `srt`, and `vtt`.
- yt-dlp usually outputs `.vtt` or `.srt`; the Python helper performs the extra cleanup needed for a readable transcript.
