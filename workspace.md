# Workspace Reference — Chele's OpenClaw Setup

*Last updated: 2026-02-14*

## Platform Configuration

**Host:** Chele's Mac mini (Apple Silicon)  
**OS:** macOS Darwin 25.3.0 (arm64)  
**OpenClaw Version:** 2026.2.9 (33c75cb)  
**Shell:** zsh  
**Gateway Mode:** Local (port 18789, loopback bind)  

### Directory Structure

```
~/.openclaw/
├── workspace/              # Primary working directory
│   ├── todos/             # Action item tracking
│   ├── memory/            # Session continuity files
│   ├── research/          # Mauboussin papers, analysis
│   ├── T4 -> /Volumes/T4  # External Thunderbolt drive
│   └── TOOLS.md           # Environment-specific notes
├── agents/                # Agent configurations
│   └── kimi/
│       └── sessions/      # Session transcripts
└── openclaw.json         # Gateway configuration
```

### T4 Drive (External Thunderbolt)

**Location:** `/Volumes/T4` (symlinked at `workspace/T4/`)  
**Note:** The entire T4 drive is configured as the Obsidian vault, not a subfolder.

| Folder | Size | Contents |
|--------|------|----------|
| `archive/` | 48K | Dated backups (2026-02-12/) |
| `obsidian/` | 0B | Empty — vault is the drive root itself |
| `openclaw/` | 122M | OpenClaw runtime data (workspace, logs, sandboxes) |
| `repos/` | 258M | Git repositories (contains `openclaw/` source) |

---

## Connected Integrations

### Telegram (Primary Channel)
- **User ID:** `@Chele_Ops` (ID: 8232947312)
- **Status:** Active
- **Use:** Primary interface for notifications and conversations
- **Features:** Topics enabled for parallel conversations

### Discord (Planned)
- **Status:** Not yet configured
- **TODO:** Create server, bot application, configure token

### Web Search
- **Provider:** Brave Search API
- **Status:** Active
- **Use:** Web searches, news, research

### Perplexity (Planned)
- **Status:** API key needed
- **Purpose:** AI-powered search with synthesized answers and citations
- **Get key:** https://www.perplexity.ai/settings/api

---

## Telegram Topic Structure

### Hashtag Conventions

| Hashtag | Purpose | Example |
|---------|---------|---------|
| `#MauboussinPrecision` | Pipeline updates for Mauboussin paper analysis | "Paper 3/17 complete: 8 metrics extracted" |
| `#cron-status` | Cron job execution reports | "#cron-status — Daily Self-Review complete" |

### Quiet Hours
- **No updates:** 9:00 PM - 6:00 AM PT
- Applies to: `#MauboussinPrecision` pipeline notifications

---

## Model Providers and Routing

### Primary Configuration

```json
{
  "primary": "moonshot/kimi-k2.5",
  "fallbacks": [
    "anthropic/claude-sonnet-4-5",
    "ollama/deepseek-r1:14b-qwen-distill-q8_0"
  ]
}
```

### Provider Details

| Provider | Model | Cost (Input/Output) | Context | Use Case |
|----------|-------|---------------------|---------|----------|
| **Moonshot** | `kimi-k2.5` | $0.60/$3.00 per M tokens | 262K | Primary — daily operations |
| **Anthropic** | `claude-sonnet-4-5` | $3.00/$15.00 per M tokens | 200K | Fallback — high-quality analysis |
| **Ollama (local)** | `deepseek-r1:14b-qwen-distill-q8_0` | $0 (local) | 131K | **DEPRECATED** — hallucination issues |

### Model Usage Policy

- **Default:** Kimi for all operations (cost-effective, good quality)
- **High-quality analysis:** Claude (Mauboussin papers, complex extraction)
- **DeepSeek:** **REMOVED from automatic fallback** — produces hallucinations and empty outputs

---

## Active Cron Jobs

All jobs send Telegram notifications with `#cron-status` tag.

| Job | Schedule | Purpose |
|-----|----------|---------|
| `qmd-embed-daily` | 3:00 AM PT daily | Update QMD embeddings for all collections |
| `morning-weather-seattle` | 6:00 AM PT daily | Weather briefing for Seattle |
| `daily-self-review` | 7:00 AM PT daily | Audit core files (MEMORY.md, SOUL.md, etc.) |
| `monthly-memory-review` | 14th of month, 9:00 AM PT | Manual MEMORY.md review reminder |
| `quarterly-api-key-rotation` | Feb/May/Aug/Nov 14th, 9:00 AM PT | Rotate API keys |

### Disabled Jobs
- `mauboussin-analysis-review` — Disabled (was reporting fake progress, counting files not quality)

---

## Backup Procedures

### Current
- T4 drive contains working copies
- Archive folder: `T4/archive/` with dated backups

### Planned
- [ ] Automated daily backup to cloud storage
- [ ] Git repository for workspace configuration files
- [ ] Encrypted backup of sensitive configs (API keys, tokens)

---

## Installed Skills

| Skill | Purpose | Status |
|-------|---------|--------|
| **qmd** | Quick Markdown Search — local hybrid search for notes | **Active** — Collections: `research`, `T4` |
| **github** | GitHub CLI integration (`gh` commands) | **Available** — Needs auth (`gh auth login`) |
| **1password** | 1Password CLI integration | Not configured |
| **nano-pdf** | PDF editing with natural language | **Active** — Installed at `/opt/homebrew/bin/nano-pdf` |
| **obsidian** | Obsidian vault automation | Not configured |

### QMD Collections

**Collection: `research`**
- Path: `/Users/chele/.openclaw/workspace/research/**/*.md`
- Files: 45 Markdown files
- Use: Mauboussin papers, analysis results, strategy docs

**Collection: `T4`**
- Path: `/Volumes/T4/**/*.md`
- Files: ~916 Markdown files
- Use: Search across entire external drive

---

## Conventions Established

### File Organization
- **`todos/`** — All action items, segmented by priority
- **`memory/`** — Session continuity (YYYY-MM-DD.md format)
- **`TOOLS.md`** — Environment-specific notes (cameras, SSH hosts, TTS preferences)
- **`workspace.md`** — This file — comprehensive reference

### Communication
- Use `#MauboussinPrecision` for pipeline updates
- Use `#cron-status` for automated job reports
- Quiet hours: 9 PM - 6 AM PT for non-urgent notifications

### Security
- Separate admin account planned (`macadmin`)
- Daily user (`chele`) will be downgraded to standard
- API key rotation: Quarterly
- File permissions: 600/700 for credentials

### Model Usage
- Kimi default for operations
- Claude for high-quality analysis (Mauboussin papers)
- **Never DeepSeek** for production (quality failures)

### Pipeline Standards
- One-at-a-time processing for quality validation
- Validate first result before continuing batch
- Stop on first garbage output
- No large PDFs (>30 pages) in automated pipelines

---

## Current Projects

### #MauboussinPrecision Pipeline
- **Status:** Active (7/17 papers complete)
- **Model:** Claude 3.5 Sonnet
- **Goal:** Extract metrics, formulas, frameworks from 17 small Mauboussin papers
- **Location:** `T4/research/mauboussin/` (papers/, results/, scripts/)
- **Completed:** Wealth Transfers, Confidence, Myth Busting, Bayes and Base Rates, New Business Boom and Bust

### Pending Security Hardening
- Tool policy lockdown
- Elevated mode sandbox fixes
- DeepSeek removal from fallback chain
- Anthropic spending limits ($5/day, $50/month)

### Planned Integrations
- Discord server + bot
- Perplexity API for AI search
- macOS Companion App

---

## Quick Reference Commands

```bash
# QMD search
qmd search "query" -c research
qmd vsearch "semantic query" -c T4
qmd embed  # Update embeddings

# GitHub (after auth)
gh auth login
gh repo list

# Gateway control
openclaw gateway restart
openclaw gateway status

# Cron management
openclaw cron list
openclaw cron run <job-id>
```

---

## Notes

- This file should be updated whenever configuration changes
- Add new integrations, skills, or conventions as they are established
- Keep TODOs in `todos/` folder, not here — this is reference only
