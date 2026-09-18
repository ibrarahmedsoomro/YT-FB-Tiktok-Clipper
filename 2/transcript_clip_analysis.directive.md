# Transcript Clip Analysis Directive

Purpose: analyze a timestamped video transcript and identify the best moments to clip.

Input:

- The agent receives or reads a transcript produced by folder `1`.
- The transcript must include timestamps or time ranges so exact clip durations can be returned.

Agent behavior:

1. Use the agent's own intelligence to understand the transcript.
2. Do not use any third-party API key or external sentiment-analysis service.
3. Find the most important, useful, emotional, surprising, or clip-worthy moments.
4. Prefer moments that can stand alone as short video clips.
5. Choose clean start and end times based on where the meaningful section begins and ends.
6. Do not explain the reasoning in the final output.

Required output:

- Create a clean output file named `clip_durations.txt`.
- The file must contain only the clip number and the time duration.
- Do not include summaries, scores, titles, reasons, notes, or extra text.

Output format:

```text
Clip 1
Time: 00:01:24 - 00:02:10

Clip 2
Time: 00:05:33 - 00:06:18
```

If only one strong clip exists, output only one clip. If multiple strong clips exist, number them in order of appearance in the video.
