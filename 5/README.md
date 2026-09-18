# Rotating Speaker Reframe

This folder renders mobile `1080x1920` versions of the clips from the original
source video. By default, the camera crop rotates between the two configured
people:

- `guest` for 3 to 4 seconds
- `host` for 2 to 3 seconds
- repeat until the clip ends

## Files

- `active_speaker_reframe.py` renders the vertical clips.
- `speakers.json` stores the left/right crop positions for this source video.
- `speaker_timeline.csv` is optional if you want manual timing later.

## Rotation Commands

Preview the rotating crop plan:

```powershell
python 5/active_speaker_reframe.py --dry-run
```

Render one clip:

```powershell
python 5/active_speaker_reframe.py --clip 1
```

Render all clips:

```powershell
python 5/active_speaker_reframe.py
```

Tune the rotation:

```powershell
python 5/active_speaker_reframe.py --primary-duration 3-4 --secondary-duration 2-3
```

Use fixed timings instead of ranges:

```powershell
python 5/active_speaker_reframe.py --primary-duration 4 --secondary-duration 2.5
```

Final videos are written to `5/vertical_clips`.

## Optional Manual Timeline Mode

If you want exact manual control, edit `speaker_timeline.csv` with absolute
timestamps from the original video:

```csv
start,end,speaker
00:03:48.000,00:03:52.400,guest
00:03:52.400,00:03:53.100,host
00:03:53.100,00:05:20.000,guest
```

Speaker names must match `speakers.json`. Any uncovered gaps use
`default_speaker`, currently `guest`.

```powershell
python 5/active_speaker_reframe.py --focus-mode timeline
```
