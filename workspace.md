# Workspace Reference — Chele's OpenClaw Setup

*Last updated: 2026-02-15*

## Platform Configuration

**Host:** Chele's Mac mini (Apple Silicon)  
**OS:** macOS Darwin 25.3.0 (arm64)  
**OpenClaw Version:** 2026.2.9 (33c75cb)  
**Shell:** zsh  
**Gateway Mode:** Local (port 18789, loopback bind)  
**Agent:** kimi (Moonshot/Kimi K2.5)  

### Directory Structure

```
~/.openclaw/
├── workspace/              # Primary working directory (Git tracked)
│   ├── AGENTS.md          # Workspace rules and conventions
│   ├── SOUL.md            # My identity and core truths
│   ├── IDENTITY.md        # Basic identity info
│   ├── TOOLS.md           # Environment-specific notes
│   ├── HEARTBEAT.md       # Heartbeat task configuration
│   ├── USER.md            # User information (currently minimal)
│   ├── workspace.md       # This file
│   ├── router.py          # Utility script
│   ├── todos/             # Action item tracking
│   ├── memory/            # Session continuity files (YYYY-MM-DD.md)
│   ├── reference-docs/    # Best practices documentation
│   ├── skills/            # Custom workspace skills
│   └── T4 -> /Volumes/T4  # External Thunderbolt drive (symlink)
├── agents/                # Agent configurations
│   └── kimi/
│       └── sessions/      # Session transcripts
├── logs/                  # Gateway logs
└── openclaw.json         # Gateway configuration
```

### T4 Drive (External Thunderbolt)

**Location:** `/Volumes/T4` (symlinked at `workspace/T4/`)  
**Note:** The entire T4 drive is the Obsidian vault, not a subfolder.

| Folder | Contents |
|--------|----------|
| `archive/` | Dated backups |
| `obsidian/` | Empty — vault is the drive root |
| `openclaw/` | OpenClaw runtime data |
| `repos/` | Git repositories (OpenClaw source) |
| `research/` | Papers, SEC filings, analysis (moved from workspace) |
| `plans/` | Planning documents (moved from workspace) |
| `vaults/` | Project designs — Omnifocus CLI (moved from workspace) |

---

## GitHub Integration

**Account:** `chele-orca`  
**Auth:** Google Sign-In + SSH key  
**SSH Key:** `~/.ssh/chele_github`  
**CLI:** `gh` authenticated

### Repositories

| Repo | Purpose | URL |
|------|---------|-----|
| `openclaw-workspace` | Workspace configuration (clean, no data) | https://github.com/chele-orca/openclaw-workspace |
| `my-test-repo` | Test repo for validation | https://github.com/chele-orca/my-test-repo |

### Git Configuration
- Protocol: SSH
- Identity: Chele (chele-orca@github.com)
- Key config: `~/.ssh/config` points to `~/.ssh/chele_github`

---

## Connected Integrations

### Telegram (Primary Channel)
- **User ID:** `@Chele_Ops` (ID: 8232947312)
- **Group:** `g-chelegroup` (-1003724723182)
- **Status:** Active
- **Use:** Primary interface for notifications and conversations
- **Features:** Topics enabled for parallel conversations
- **Security:** `requireMention: false` (intentional — only user + Chele in group)

### Web Search
- **Provider:** Brave Search API
- **Status:** Active
- **Use:** Web searches, news, research

### Perplexity (Planned)
- **Status:** API key needed
- **Purpose:** AI-powered search with synthesized answers

---

## Telegram Topic Structure

### Hashtag Conventions

| Hashtag | Purpose | Example |
|---------|---------|---------|
| `#cron-status` | Cron job execution reports | "#cron-status — Daily Self-Review complete" |

### Quiet Hours
- **No updates:** 9:00 PM - 6:00 AM PT
- Applies to non-urgent notifications

---

## Model Providers and Routing

### Primary Configuration

```json
{
  "primary": "moonshot/kimi-k2.5",
  "fallbacks": [
    "anthropic/claude-sonnet-4-5"
  ]
}
```

### Provider Details

| Provider | Model | Cost (Input/Output) | Context | Use Case |
|----------|-------|---------------------|---------|----------|
| **Moonshot** | `kimi-k2.5` | $0.60/$3.00 per M tokens | 262K | Primary — daily operations |
| **Anthropic** | `claude-sonnet-4-5` | $3.00/$15.00 per M tokens | 200K | Fallback — high-quality analysis |

### Notes
- DeepSeek removed from fallbacks due to hallucination issues
- Ollama available locally but not in automatic fallback chain

---

## Active Cron Jobs

All jobs send Telegram notifications with `#cron-status` tag.

| Job | Schedule | Purpose | Status |
|-----|----------|---------|--------|
| `qmd-embed-daily` | 3:00 AM PT daily | Update QMD embeddings | ⚠️ Error (announce delivery) |
| `morning-weather-seattle` | 6:00 AM PT daily | Weather briefing | ✅ OK |
| `daily-self-review` | 7:00 AM PT daily | Audit core files | ✅ OK |
| `monthly-memory-review` | 14th, 9:00 AM PT | MEMORY.md review reminder | Scheduled |
| `quarterly-api-key-rotation` | Feb/May/Aug/Nov 14th | API key rotation | Scheduled |

### Notes
- `mauboussin-analysis-review` — Disabled (reporting fake progress)
- Next monthly review: March 14, 2026
- Next API key rotation: May 14, 2026

---

## Backup Procedures

### Current
- T4 drive contains working copies
- Archive folder: `T4/archive/` with dated backups
- **Git:** Workspace config backed up to `chele-orca/openclaw-workspace`

### What's in Git vs T4

| Location | Contents |
|----------|----------|
| **Git (openclaw-workspace)** | Config files, memory/, todos/, reference-docs/, skills/ |
| **T4 only** | research/ (papers, filings), vaults/ (project designs), plans/ |

---

## Installed Skills

### Custom Workspace Skills

| Skill | Purpose | Location |
|-------|---------|----------|
| **exa-search** | Neural/semantic web search via Exa.ai | `skills/exa-search/` |

### System Skills (Available)

| Skill | Purpose |
|-------|---------|
| 1password | 1Password CLI integration |
| coding-agent | Run Codex CLI, Claude Code, etc. |
| github | GitHub CLI (`gh`) operations |
| healthcheck | Security hardening and audits |
| himalaya | Email management via IMAP/SMTP |
| model-usage | CodexBar usage summaries |
| nano-pdf | PDF editing with natural language |
| obsidian | Obsidian vault automation |
| session-logs | Search session transcripts |
| skill-creator | Create/update AgentSkills |
| summarize | Extract text from URLs/podcasts |
| tmux | Remote tmux control |
| weather | Current weather and forecasts |

---

## Conventions Established

### File Organization
- **`todos/`** — Action items (AUDIT-RESULTS.md, todo.md, COMPLETED-*.md)
- **`memory/`** — Session continuity (YYYY-MM-DD.md format)
- **`reference-docs/`** — Best practices documentation
- **`skills/`** — Custom workspace skills only
- **`.gitignore`** — Excludes: research/, vaults/, .DS_Store, *.pdf, etc.

### Git Workflow
- Workspace config → `openclaw-workspace` repo
- SSH authentication for unattended pushes
- Large data files excluded from Git (stay on T4)

### Communication
- Use `#cron-status` for automated job reports
- Quiet hours: 9 PM - 6 AM PT for non-urgent notifications

### Security
- Gateway bind: `loopback` (not LAN)
- File permissions: 600/700 for credentials
- DM policy: `pairing` (not `open`)
- Group policy: `allowlist`
- API key rotation: Quarterly (automated reminder)

### Model Usage
- Kimi default for operations
- Claude for high-quality analysis
- DeepSeek **not used** for production

---

## Quick Reference Commands

```bash
# Git operations (as chele-orca)
gh repo list
git push origin main

# Cron management
openclaw cron list
openclaw cron run <job-id>

# Gateway control
openclaw gateway restart
openclaw gateway status

# SSH test
cd ~/.openclaw/workspace
ssh -T git@github.com
```

---

## Notes

- Update this file whenever configuration changes
- Keep TODOs in `todos/` folder, not here — this is reference only
- GitHub repo: https://github.com/chele-orca/openclaw-workspace
- T4 holds all data/research — workspace holds only config
