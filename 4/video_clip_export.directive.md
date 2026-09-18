# Video Clip Export Directive

Purpose: cut the downloaded full video into clips using the durations from folder `2`.

Input:

- Full downloaded video from `3/downloads`.
- Clip timing file from `2/clip_durations.txt`.

Agent behavior:

1. Read `2/clip_durations.txt`.
2. Find the downloaded `.mp4` source video in `3/downloads`.
3. Use FFmpeg for fast local cutting and exporting.
4. Create one output file per clip.
5. Save final clips inside `4/clips`.
6. Each exported clip must match the start and end time written in folder `2`.
7. Do not re-analyze the transcript in this step.
8. Do not download the YouTube video again in this step.

Default command:

```bash
python 4/cut_clips.py
```

Output format:

```text
4/clips/clip_01.mp4
4/clips/clip_02.mp4
4/clips/clip_03.mp4
```

Notes:

- Default mode uses FFmpeg re-encoding for cleaner, more accurate clip boundaries.
- For the fastest possible export, use `--mode copy`, but clip boundaries may land on nearby keyframes.
- For vertical short-form output, use `--resize vertical`.
