# Cleanup Directive

## Purpose

Reset the project to a clean, ready-to-run state by deleting generated pipeline outputs and Python cache artifacts that are excluded by the repository's `.gitignore`.

## Required Procedure

1. Work from the repository root—the directory containing this file, `.gitignore`, and folders `1` through `6`.
2. Read `.gitignore` before deleting anything. Treat it as the authoritative list of generated or disposable artifacts.
3. Delete only the ignored outputs listed below:
   - Every `.srt` file directly inside `1/`.
   - `2/clip_durations.txt`.
   - Every item inside `3/downloads/` except `.gitkeep`.
   - Every item inside `4/clips/` except `.gitkeep`.
   - Every item inside `5/vertical_clips/` except `.gitkeep`.
   - Every item inside `6/captioned_clips/` except `.gitkeep`.
   - Every `__pycache__/` directory anywhere in the repository.
   - Every `*.pyc` and `*.pyo` file anywhere in the repository.
4. If an output path does not exist or is already empty, continue without treating that as an error.
5. After cleanup, verify that all listed generated outputs and cache artifacts are gone and that each output directory still exists with its `.gitkeep` file intact.
6. Report what was removed and confirm that the project is ready for a fresh pipeline run.

## Safety Rules

- Never delete `.git/`, `.gitignore`, `AGENTS.md`, `cleanup.md`, directive files, README files, Python source files, or configuration files.
- Preserve `3/downloads/.gitkeep`, `4/clips/.gitkeep`, `5/vertical_clips/.gitkeep`, and `6/captioned_clips/.gitkeep`.
- Do not delete the output directories themselves; delete only their generated contents.
- Do not use broad deletion commands that can remove untracked source or project files. Delete only the explicit paths and patterns defined above.
- Do not run any pipeline step or generate replacement outputs during cleanup.
- If `.gitignore` has changed and conflicts with this list, stop and reconcile the cleanup targets with `.gitignore` before deleting anything.
