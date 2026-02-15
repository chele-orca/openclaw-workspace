# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

## T4 Drive (External Thunderbolt)

**Location:** `/Volumes/T4` (symlinked at `workspace/T4/`)

**Note:** The entire T4 drive is configured as the Obsidian vault, not a subfolder.

### Directory Structure

| Folder | Size | Contents | Notes |
|--------|------|----------|-------|
| `archive/` | 48K | Dated backups (2026-02-12/) | Minimal usage |
| `obsidian/` | 0B | **Empty** — Not the vault folder | Entire T4 drive IS the Obsidian vault |
| `openclaw/` | 122M | OpenClaw runtime data | Workspace, logs, sandboxes |
| `repos/` | 258M | Git repositories | Contains `openclaw/` source code |

**Markdown files found:** ~916 total (791 in repos, 123 in openclaw, 0 in obsidian)

**Note:** QMD indexed the T4 drive but reported 29,469 files — this appears to be an error or indexing artifact. Actual count is <1,000 MD files.

## QMD Collections

**Collection: `research`**
- Path: `/Users/chele/.openclaw/workspace/research/**/*.md`
- Files: 45 Markdown files
- Use: Search Mauboussin papers, analysis results, strategy docs
- Command: `qmd search "query" -c research`

**Collection: `T4`**
- Path: `/Volumes/T4/**/*.md`
- Files: ~916 Markdown files (mostly OpenClaw source/docs)
- Use: Search across external drive
- Command: `qmd search "query" -c T4`

## Search Tips

- Use `qmd search` (BM25) for fast keyword matching — typically instant
- Use `qmd vsearch` only when keyword search fails — can take ~1 min on cold start
- Use `qmd query` sparingly — hybrid + LLM reranking, often slow/timeout
- Run `qmd embed` after adding new files to update embeddings
