# OpenClaw Skills Installation Report

## Environment Status
- **Current Environment**: Sandboxed Debian container (read-only filesystem)
- **Target Environment**: macOS host (Chele's Mac mini) - Darwin 25.3.0
- **Limitation**: Cannot directly install on host from sandbox

## Skills Installation Requirements

### 1. github
**Typical Requirements:**
- `gh` - GitHub CLI tool
- `git` - Version control

**Installation Commands (for host):**
```bash
brew install gh git
```

**Verification:**
```bash
openclaw skills info github
```

---

### 2. coding-agent
**Typical Requirements:**
- `aider` - AI coding assistant (Python package)
- OR `claude-code` - Anthropic's coding agent

**Installation Commands (for host):**
```bash
# Option 1: Aider
pip install aider-chat

# Option 2: Claude Code
npm install -g @anthropic-ai/claude-code
```

**Verification:**
```bash
openclaw skills info coding-agent
```

---

### 3. discord
**Typical Requirements:**
- `discord webhook` capabilities OR
- `curl` for webhook POSTs (usually built-in)

**Installation Commands (for host):**
```bash
# Usually no additional binaries needed - uses curl
# May need webhook URL configuration
```

**Verification:**
```bash
openclaw skills info discord
```

---

### 4. tmux
**Typical Requirements:**
- `tmux` - Terminal multiplexer

**Installation Commands (for host):**
```bash
brew install tmux
```

**Verification:**
```bash
openclaw skills info tmux
```

---

### 5. blogwatcher
**Typical Requirements:**
- `curl` or `wget` for fetching feeds
- May need RSS parsing tools

**Installation Commands (for host):**
```bash
# Usually no additional binaries needed
# May need Python/Node dependencies
```

**Verification:**
```bash
openclaw skills info blogwatcher
```

---

### 6. summarize
**Typical Requirements:**
- AI API access (OpenAI, Anthropic, etc.)
- `curl` for API calls
- OR local LLM setup

**Installation Commands (for host):**
```bash
# May need API key configuration
# Usually no additional binaries needed
```

**Verification:**
```bash
openclaw skills info summarize
```

---

### 7. session-logs
**Typical Requirements:**
- Log rotation tools (usually built-in)
- File management utilities

**Installation Commands (for host):**
```bash
# Usually no additional binaries needed
```

**Verification:**
```bash
openclaw skills info session-logs
```

---

## Recommended Installation Order

1. **Start with base tools:**
   ```bash
   brew install gh git tmux curl
   ```

2. **Install Python/Node tools if needed:**
   ```bash
   pip install aider-chat
   # or
   npm install -g @anthropic-ai/claude-code
   ```

3. **Verify OpenClaw CLI is installed:**
   ```bash
   which openclaw
   openclaw --version
   ```

4. **Check each skill status:**
   ```bash
   for skill in github coding-agent discord tmux blogwatcher summarize session-logs; do
       echo "=== $skill ==="
       openclaw skills info $skill
   done
   ```

## Manual Steps Required

Since I cannot access the host macOS system directly, please run the following on the host:

```bash
# 1. Ensure OpenClaw CLI is installed
openclaw --version

# 2. Install base dependencies
brew install gh git tmux

# 3. Install Python tools if using aider
pip3 install aider-chat

# 4. Verify each skill
openclaw skills info github
openclaw skills info coding-agent
openclaw skills info discord
openclaw skills info tmux
openclaw skills info blogwatcher
openclaw skills info summarize
openclaw skills info session-logs
```

## Skills Status Summary

| Skill | Status | Binaries Needed | Notes |
|-------|--------|-----------------|-------|
| github | ⏳ Pending Install | gh, git | Run on host |
| coding-agent | ⏳ Pending Install | aider or claude-code | Python/npm package |
| discord | ⏳ Pending Install | curl (built-in) | Webhook config needed |
| tmux | ⏳ Pending Install | tmux | Brew install |
| blogwatcher | ⏳ Pending Install | curl (built-in) | RSS feed config |
| summarize | ⏳ Pending Install | API key | AI service config |
| session-logs | ⏳ Pending Install | None | Built-in tools |

---

*Report generated: 2026-02-14*
*Environment: Sandboxed container (cannot install directly on host)*
