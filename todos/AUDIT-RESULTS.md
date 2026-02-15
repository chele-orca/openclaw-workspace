# OpenClaw Configuration Audit — 2026-02-14

**Auditor:** Subagent (overnight-audit)  
**Date:** 2026-02-14 20:20 PT  
**Status:** ⚠️ **PARTIAL** — Sandbox restrictions prevented full config access

---

## 🚫 Access Limitations

**Cannot access from sandbox:**
- `~/.openclaw/openclaw.json` — main configuration file
- `/Users/chele/.openclaw/workspace/T4/` — external Thunderbolt drive (outside sandbox)

**Reason:** Subagents run in Docker sandbox with restricted filesystem access.

---

## 📋 Current Configuration (from workspace.md reference)

### Session Settings
- **Default model:** `moonshot/kimi-k2.5`
- **Heartbeat interval:** 60 minutes (configured, requires gateway restart)
- **Session expiration:** Default (daily reset)
- **Session store:** Not documented

### Fallback Chain
```json
{
  "primary": "moonshot/kimi-k2.5",
  "fallbacks": [
    "anthropic/claude-sonnet-4-5",
    "ollama/deepseek-r1:14b-qwen-distill-q8_0"
  ]
}
```

### Model Routing
- Primary operations: Kimi (cost-effective)
- High-quality analysis: Claude (Mauboussin papers)
- Local fallback: DeepSeek (documented as problematic)

---

## 🎯 Desired State

### Session Settings
- **Session expiration:** 365 days (one year)
  - Rationale: Using Telegram topics for scoped conversations
  - Current: Daily reset (needs change)
  - Config: `"store": "persistent", "expiresIn": "365d"`

### Fallback Chain
- **Remove DeepSeek:** ❌ Currently in fallback chain
  - Issue: Produces hallucinations and empty outputs
  - Evidence: Only 2/39 analyses valid (5% success rate)
  - Action: Remove `ollama/deepseek-r1:14b-qwen-distill-q8_0` from fallbacks
  - Status: **CRITICAL** — affects data quality

### Spending Limits
- **Anthropic limits:** Not configured
  - Desired: $5/day, $50/month with alerts
  - Current: Unknown (no access to config)

---

## ✅ Recommendations

### High Priority
1. **Remove DeepSeek from fallback chain** — CRITICAL quality issue
2. **Set session expiration to 365 days** — enables long-running conversations
3. **Configure Anthropic spending limits** — $5/day, $50/month

### Medium Priority
4. **Restart gateway** — apply heartbeat interval change (60 min)
5. **Document actual config** — requires reading openclaw.json from host
6. **Tool policy lockdown** — restrict dangerous operations
7. **Configure SOUL.md security constraints** — per OpenClaw best practices

---

## 🔍 Next Steps

**User actions required:**
1. Read `~/.openclaw/openclaw.json` from host (not sandbox)
2. Verify current fallback chain contains DeepSeek
3. Edit config to remove DeepSeek and set session expiration
4. Restart gateway: `openclaw gateway restart`
5. Test with: `openclaw gateway status`

**Documentation:**
- Update `workspace.md` with actual config once verified
- Track changes in `memory/2026-02-14.md`

---

## 📌 Security Notes

- **Subagent sandbox:** Cannot modify system config (by design)
- **Manual verification needed:** All findings based on workspace documentation
- **Config backup recommended:** Before making changes to openclaw.json

---

*This audit is incomplete due to sandbox restrictions. Full audit requires host access to ~/.openclaw/openclaw.json.*
