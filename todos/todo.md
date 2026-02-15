# Master Todo List

## High Priority — Do Soon

- [x] **~~Heartbeat interval to 60 minutes~~** — COMPLETE
  - Configured to 60 minutes
  - Will take effect on next gateway restart
  - Keeps Kimi as the model, cuts costs in half

- [x] **~~Telegram Topics group~~** — COMPLETE
  - Group: `-1003724723182`
  - Topics: #MauboussinPrecision (23), cron-status (26)
  - Active and receiving updates

- [x] **~~Daily self-review cron~~** — COMPLETE
  - Chele audits its own config/memory files each morning
  - Flag inconsistencies, stale data, or issues

- [x] **~~Monthly MEMORY.md review~~** — COMPLETE
  - Calendar reminder to manually review
  - Archive old entries, update priorities

## Medium Priority — Do When Convenient

- [ ] **GitHub skill setup**
  - Create fine-grained personal access token at https://github.com/settings/personal-access-tokens/new
    - Name: "OpenClaw"
    - Expiration: 90 days (for rotation practice)
    - Repositories: All repositories (or select specific)
    - Permissions:
      - Contents: Read
      - Issues: Read/Write
      - Pull requests: Read/Write
      - Actions: Read
      - Members: Read (if org access needed)
  - Run `gh auth login` and paste token
  - Test with `gh repo list`
  - Reference: `/opt/homebrew/lib/node_modules/openclaw/skills/github/SKILL.md`

- [ ] **Discord setup**
  - Create Discord server
  - Create bot application at https://discord.com/developers/applications
  - Connect to OpenClaw, test message routing

- [ ] **OmniFocus skill setup**
  - Located at `vaults/omnifocus-cli/`
  - Configure OmniFocus CLI integration
  - Set up task automation from OpenClaw

- [ ] **macOS companion app**
  - Menu bar interface for gateway control
  - Download from OpenClaw releases

- [x] **~~Finish installing Exa Search skill~~** — COMPLETE
  - Located at `/Users/chele/.openclaw/workspace/skills/exa-search/`
  - API key configured: `EXA_API_KEY`
  - Tested successfully: Found Mauboussin ROIC resources ($0.0050/3 results)
  - Ready for neural/semantic web search

- [ ] **Perplexity API key**
  - Get at https://www.perplexity.ai/settings/api
  - Built-in OpenClaw provider — switch via config change
  - AI-powered search with citations vs raw links

- [ ] **Firewall hardening**
  - Block all incoming connections
  - Enable stealth mode (no response to pings)

- [x] **~~SSH via Tailscale~~** — COMPLETE
  - Enable Remote Login for remote management
  - Restrict to Tailscale network only

- [ ] **Always-on hardening**
  - Auto-start after power failure
  - Wake for network access

- [ ] **Enable HTTP(S) inbound connections**
  - Currently only SSL/WebSocket inbound is supported
  - Configure OpenClaw to accept plain HTTP/HTTPS requests
  - Useful for webhooks, API integrations, health checks

- [ ] **Update cron jobs to use Telegram Topics**
  - Group: `-1003724723182`
  - Cron status topic: `26`
  - #MauboussinPrecision topic: `23`
  - Requires recreating cron jobs with threadId support
  - Currently cron jobs route to private DM instead of group topics

## Low Priority

- [x] **~~QMD improvements~~** — Mauboussin project reorganized
  - Moved to clean T4 location: `T4/research/mauboussin/`
  - Structure: `papers/` (43 PDFs), `results/` (39 analyses), `scripts/`
  - Update pipeline to use new paths (in progress)

- [ ] **Set session expiration to one year**
  - Change from default daily reset to 365-day expiration
  - Rationale: Using Telegram topic channels to keep conversations scoped
  - Requires editing `~/.openclaw/openclaw.json` and restarting gateway
  - Add to session config: `"store": "persistent", "expiresIn": "365d"`

- [ ] **Sandbox Infrastructure — Evaluate making PDF tools available**
  - Python with PyPDF2/pdfplumber for PDF text extraction
  - pdftotext (poppler-utils) as alternative
  - Node.js with pdf-parse for JavaScript-based extraction
  - Weigh security implications of adding these to sandbox vs. host-only processing
  - Current workaround: Host extracts text, sub-agent analyzes

- [ ] **Fix zsh completion error**
  - Error: `/Users/chele/.openclaw/completions/openclaw.zsh:3579: command not found: compdef`
  - Likely fix: Ensure `compinit` is loaded before OpenClaw completions in `.zshrc`

---

## Security Section

### Account Security
- [ ] **Create separate admin account (`macadmin`) and downgrade `chele` to standard**
  - Create new admin account with full privileges
  - Remove admin rights from daily user
  - Use admin only for system changes

- [ ] **Lock down file permissions**
  - Review permissions on sensitive directories (`~/.openclaw/`, `~/Documents`)
  - Ensure credential files are 600/700 (not world-readable)
  - Audit Downloads/Desktop for overly permissive access
  - Consider enabling FileVault for full-disk encryption

### OpenClaw Security
- [ ] **Tool policy lockdown** — deny dangerous tools, restrict high-risk operations
- [ ] **Elevated mode** — disable sandbox escapes, prevent privilege escalation
- [ ] **Remove DeepSeek from main fallback chain** — CRITICAL, affecting data quality
- [ ] **Anthropic spending limits** — $5/day, $50/month, with alerts
- [ ] **Configure SOUL.md security constraints**
  - Reference: https://robertheubanks.substack.com/i/187294099/step-31-configure-soulmd-security-constraints

