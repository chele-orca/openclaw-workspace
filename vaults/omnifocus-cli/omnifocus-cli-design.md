# OmniFocus CLI Design Document

## Overview

A modern Node.js CLI tool that wraps JXA (JavaScript for Automation) to provide comprehensive OmniFocus functionality for OpenClaw integration. This tool enables programmatic task and project management on macOS.

---

## 1. CLI Command Structure and Subcommands

### Command Naming Convention
Following OpenClaw patterns (like `obsidian-cli`), the tool will be named `omnifocus-cli` with the binary name `of`.

### Top-Level Structure

```
of <command> [options] [arguments]
```

### Subcommands

#### 1.1 Task Management

##### `of create [task-name]`
Create a new task in OmniFocus.

**Options:**
- `-p, --project <name>` - Assign to project (creates if doesn't exist)
- `-c, --context <name>` - Assign context/tag
- `-d, --due <date>` - Due date (natural language: "today", "tomorrow", "+3 days")
- `-D, --defer <date>` - Defer date (natural language)
- `-n, --note <text>` - Add note to task
- `-f, --flag` - Flag the task
- `--transport` - Copy task as transport text instead of creating

**Examples:**
```bash
of create "Buy groceries" --due "today" --context " errands"
of create "Review PR" --project "Work" --due "tomorrow 5pm" --flag
```

##### `of list [options]`
Query and list tasks with filtering.

**Options:**
- `-p, --project <name>` - Filter by project
- `-c, --context <name>` - Filter by context
- `-s, --status <status>` - Filter by status: `active`, `completed`, `dropped`, `flagged`, `overdue`
- `-d, --due-before <date>` - Tasks due before date
- `-D, --defer-after <date>` - Tasks deferred after date
- `-l, --limit <n>` - Limit results (default: 50)
- `-j, --json` - Output as JSON

**Examples:**
```bash
of list --status overdue --json
of list --project "Work" --limit 10
```

##### `of complete <task-id>`
Mark a task as complete.

**Options:**
- `-u, --uncomplete` - Mark as incomplete instead
- `-a, --all-matching` - Complete all matching tasks (when using --project/--context filters)

**Examples:**
```bash
of complete abc123
of complete --project "Shopping" --all-matching
```

##### `of show <task-id>`
Display detailed information about a specific task.

**Options:**
- `-j, --json` - Output as JSON

---

#### 1.2 Project Management

##### `of project create <name>`
Create a new project.

**Options:**
- `-f, --folder <name>` - Place in folder (creates if doesn't exist)
- `-s, --status <status>` - Project status: `active`, `on-hold`, `dropped`, `completed`
- `-n, --note <text>` - Add note to project
- `-d, --due <date>` - Project due date

**Examples:**
```bash
of project create "Website Redesign" --folder "Work"
of project create "Personal Goals" --status on-hold
```

##### `of project list [options]`
List projects.

**Options:**
- `-f, --folder <name>` - Filter by folder
- `-s, --status <status>` - Filter by status
- `-j, --json` - Output as JSON

---

#### 1.3 Context/Tag Management

##### `of context list`
List all contexts/tags.

**Options:**
- `-j, --json` - Output as JSON

---

#### 1.4 Utility Commands

##### `of transport [task-name]`
Generate OmniFocus transport text for quick capture.

**Options:**
- Same as `create` command

**Examples:**
```bash
of transport "Buy milk @errands (today)"
# Output: - Buy milk @errands //today
```

##### `of inbox`
List inbox items.

**Options:**
- `-j, --json` - Output as JSON
- `-l, --limit <n>` - Limit results

---

## 2. JXA Scripts Architecture

### Directory Structure

```
lib/
├── jxa/
│   ├── index.js          # JXA runner wrapper
│   ├── create-task.js    # Task creation JXA
│   ├── query-tasks.js    # Task querying JXA
│   ├── complete-task.js  # Task completion JXA
│   ├── create-project.js # Project creation JXA
│   ├── list-projects.js  # Project listing JXA
│   └── utils.js          # JXA utilities (date parsing, etc.)
├── parsers/
│   └── date-parser.js    # Natural language date parsing
└── formatters/
    ├── json-formatter.js # JSON output formatting
    └── text-formatter.js # Human-readable output
```

### JXA Script Descriptions

#### 2.1 `create-task.js`
Creates a task in OmniFocus with full property support.

**Input Parameters:**
```javascript
{
  name: string,
  note: string | null,
  projectName: string | null,
  contextName: string | null,
  dueDate: Date | null,
  deferDate: Date | null,
  flagged: boolean
}
```

**JXA Implementation Strategy:**
```javascript
// Core logic outline
const app = Application('OmniFocus');
app.includeStandardAdditions = true;

// Find or create project
// Find or create context
// Create task with properties
// Return task ID and name
```

**Return Value:**
```javascript
{
  success: boolean,
  taskId: string,
  taskName: string,
  project: string | null,
  context: string | null
}
```

#### 2.2 `query-tasks.js`
Queries tasks based on filter criteria.

**Input Parameters:**
```javascript
{
  projectName: string | null,
  contextName: string | null,
  status: 'active' | 'completed' | 'dropped' | 'flagged' | 'overdue' | null,
  dueBefore: Date | null,
  deferAfter: Date | null,
  limit: number
}
```

**JXA Implementation Strategy:**
```javascript
// Access default document
const doc = app.defaultDocument;

// Build where clauses dynamically
// Support for: flattenedTasks, tasks matching predicates
// Return array of task objects with essential properties
```

**Return Value:**
```javascript
{
  success: boolean,
  count: number,
  tasks: Array<{
    id: string,
    name: string,
    project: string | null,
    context: string | null,
    dueDate: string | null,
    deferDate: string | null,
    completed: boolean,
    flagged: boolean
  }>
}
```

#### 2.3 `complete-task.js`
Marks tasks as complete or incomplete.

**Input Parameters:**
```javascript
{
  taskId: string | null,
  projectName: string | null,
  contextName: string | null,
  uncomplete: boolean,
  allMatching: boolean
}
```

**Return Value:**
```javascript
{
  success: boolean,
  completedCount: number,
  tasks: Array<{ id: string, name: string }>
}
```

#### 2.4 `create-project.js`
Creates projects with optional folder hierarchy.

**Input Parameters:**
```javascript
{
  name: string,
  folderName: string | null,
  note: string | null,
  status: 'active' | 'on-hold' | 'dropped' | 'completed',
  dueDate: Date | null
}
```

**JXA Implementation Strategy:**
```javascript
// Find or create folder if specified
// Create project with properties
// Return project details
```

**Return Value:**
```javascript
{
  success: boolean,
  projectId: string,
  projectName: string,
  folder: string | null
}
```

#### 2.5 `list-projects.js`
Lists all projects with optional filtering.

**Input Parameters:**
```javascript
{
  folderName: string | null,
  status: string | null
}
```

**Return Value:**
```javascript
{
  success: boolean,
  count: number,
  projects: Array<{
    id: string,
    name: string,
    folder: string | null,
    status: string,
    numberOfTasks: number,
    numberOfAvailableTasks: number
  }>
}
```

#### 2.6 `list-contexts.js`
Lists all contexts/tags.

**Return Value:**
```javascript
{
  success: boolean,
  count: number,
  contexts: Array<{
    id: string,
    name: string,
    numberOfTasks: number
  }>
}
```

### JXA Runner Pattern

```javascript
// lib/jxa/index.js
const { exec } = require('child_process');
const path = require('path');

function runJxa(scriptName, params) {
  const scriptPath = path.join(__dirname, `${scriptName}.js`);
  const jsonParams = JSON.stringify(params);
  
  return new Promise((resolve, reject) => {
    const cmd = `osascript -l JavaScript -e '
      const params = JSON.parse(decodeURIComponent("${encodeURIComponent(jsonParams)}"));
      ${fs.readFileSync(scriptPath, 'utf8')}
    '`;
    
    exec(cmd, { timeout: 30000 }, (error, stdout, stderr) => {
      // Handle execution and parse JSON output
    });
  });
}
```

---

## 3. Package.json Dependencies

### Core Dependencies

```json
{
  "name": "omnifocus-cli",
  "version": "1.0.0",
  "description": "CLI tool for OmniFocus task management via JXA",
  "main": "index.js",
  "bin": {
    "of": "./bin/of.js",
    "omnifocus-cli": "./bin/of.js"
  },
  "scripts": {
    "test": "jest",
    "lint": "eslint ."
  },
  "keywords": ["omnifocus", "gtd", "cli", "jxa", "automation"],
  "author": "",
  "license": "MIT",
  "engines": {
    "node": ">=18.0.0"
  },
  "os": ["darwin"],
  "dependencies": {
    "commander": "^11.1.0",
    "chalk": "^4.1.2",
    "date-fns": "^2.30.0",
    "date-fns-tz": "^2.0.0"
  },
  "devDependencies": {
    "jest": "^29.7.0",
    "eslint": "^8.54.0"
  }
}
```

### Dependency Justifications

| Package | Version | Purpose |
|---------|---------|---------|
| `commander` | ^11.1.0 | CLI argument parsing, subcommand structure, help generation |
| `chalk` | ^4.1.2 | Terminal color output for human-readable formatting |
| `date-fns` | ^2.30.0 | Date parsing, manipulation, and formatting |
| `date-fns-tz` | ^2.0.0 | Timezone support for due/defer dates |

### Why Chalk v4 instead of v5?
Chalk v5 is ESM-only. Using v4 maintains CommonJS compatibility for broader Node.js version support without requiring ES module configuration.

---

## 4. Installation Method

### Option A: npm Global Installation (Recommended)

```bash
npm install -g omnifocus-cli
```

**Pros:**
- Simple one-command installation
- Available system-wide
- Easy updates via `npm update -g omnifocus-cli`

**Cons:**
- Requires npm/node installation
- Permission issues on some systems (use `npx` alternative)

### Option B: Local Installation

```bash
npm install omnifocus-cli
npx of --help
```

**Pros:**
- No global permission issues
- Version pinning per project
- Works with npm workspaces

**Cons:**
- Requires `npx` prefix or npm script wrapper

### Option C: Homebrew (Future)

```bash
brew install omnifocus-cli
```

**Consideration:** Could be added later for non-Node users.

### Recommended Approach

**Primary:** npm global installation with preinstall check:

```javascript
// preinstall.js
const { platform } = require('os');

if (platform() !== 'darwin') {
  console.error('omnifocus-cli only works on macOS (OmniFocus is macOS-only)');
  process.exit(1);
}
```

**Package.json engines field:**
```json
{
  "os": ["darwin"],
  "engines": {
    "node": ">=18.0.0"
  }
}
```

---

## 5. OpenClaw Skill Integration Approach

### 5.1 Skill Structure

```
skills/
└── omnifocus/
    ├── SKILL.md
    ├── config.yaml
    └── tools/
        ├── create_task.yaml
        ├── list_tasks.yaml
        ├── complete_task.yaml
        └── create_project.yaml
```

### 5.2 Tool Definitions

Each tool maps to a CLI command with JSON output:

#### `create_task.yaml`
```yaml
name: create_task
description: Create a new task in OmniFocus
command: "of create {{name}} {{#if project}}--project '{{project}}'{{/if}} {{#if context}}--context '{{context}}'{{/if}} {{#if due}}--due '{{due}}'{{/if}} {{#if defer}}--defer '{{defer}}'{{/if}} {{#if note}}--note '{{note}}'{{/if}} {{#if flag}}--flag{{/if}} --json"
parameters:
  - name: name
    type: string
    required: true
  - name: project
    type: string
    required: false
  - name: context
    type: string
    required: false
  - name: due
    type: string
    required: false
  - name: defer
    type: string
    required: false
  - name: note
    type: string
    required: false
  - name: flag
    type: boolean
    required: false
```

#### `list_tasks.yaml`
```yaml
name: list_tasks
description: List tasks from OmniFocus with optional filters
command: "of list {{#if project}}--project '{{project}}'{{/if}} {{#if context}}--context '{{context}}'{{/if}} {{#if status}}--status {{status}}{{/if}} {{#if due_before}}--due-before '{{due_before}}'{{/if}} --json"
parameters:
  - name: project
    type: string
    required: false
  - name: context
    type: string
    required: false
  - name: status
    type: string
    enum: [active, completed, dropped, flagged, overdue]
    required: false
  - name: due_before
    type: string
    required: false
```

### 5.3 Natural Language Integration

The CLI's date parser enables OpenClaw to use natural language:

```yaml
# In SKILL.md examples
examples:
  - user: "Add a task to buy milk today"
    tool: create_task
    params:
      name: "Buy milk"
      due: "today"
      
  - user: "What tasks are due this week?"
    tool: list_tasks
    params:
      due_before: "next monday"
```

### 5.4 Output Parsing

CLI returns structured JSON that OpenClaw can parse:

```javascript
// Example response processing
const result = JSON.parse(stdout);
if (result.success) {
  return `Created task "${result.taskName}"${result.project ? ` in project "${result.project}"` : ''}`;
} else {
  throw new Error(result.error);
}
```

---

## 6. Security Considerations

### 6.1 macOS Automation Permissions

OmniFocus CLI requires macOS automation permissions:

1. **Accessibility Permissions** - Not required for JXA
2. **Automation Permissions** - System Preferences > Security & Privacy > Privacy > Automation

**First Run Experience:**
```javascript
// lib/utils/check-permissions.js
const { exec } = require('child_process');

function checkAutomationPermissions() {
  return new Promise((resolve) => {
    exec('osascript -e \'tell application "OmniFocus" to name\'', (error) => {
      if (error && error.message.includes('not allowed')) {
        console.error(chalk.yellow('⚠️  Automation permission required'));
        console.log('Please grant permission in:');
        console.log('System Preferences > Security & Privacy > Privacy > Automation');
        resolve(false);
      } else {
        resolve(true);
      }
    });
  });
}
```

### 6.2 Code Signing and Notarization

**Development:** No special requirements

**Distribution:** 
- For wide distribution, consider code signing
- Self-signed packages may trigger Gatekeeper warnings
- npm installation bypasses most Gatekeeper issues

### 6.3 Input Sanitization

**Shell Injection Prevention:**
```javascript
// lib/utils/sanitize.js
function sanitizeForShell(input) {
  // Escape single quotes by ending string, adding escaped quote, restarting
  return input.replace(/'/g, "'\"'\"'");
}

function sanitizeForJXA(input) {
  // Escape for JavaScript string context
  return input
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/"/g, '\\"')
    .replace(/\n/g, '\\n');
}
```

**JSON Parameter Encoding:**
```javascript
// Pass parameters via JSON to avoid shell parsing issues
const params = encodeURIComponent(JSON.stringify(args));
```

### 6.4 OmniFocus Data Access

**Scope:** The CLI can:
- Read all tasks, projects, and contexts
- Create and modify tasks/projects
- Mark tasks complete

**Limitations:**
- Cannot access OmniFocus preferences
- Cannot modify OmniFocus settings
- Cannot delete items (only mark dropped)

### 6.5 Best Practices

1. **Audit Trail:** Log all JXA executions for debugging
2. **Error Masking:** Don't expose internal paths in error messages to users
3. **Rate Limiting:** Consider adding delays for bulk operations
4. **Backup Warning:** Display warning when creating bulk operations

```javascript
// Example warning for bulk operations
if (options.allMatching) {
  console.log(chalk.yellow('⚠️  This will affect multiple tasks. Proceed? [y/N]'));
  // ... confirmation logic
}
```

---

## 7. Error Handling Strategy

### JXA Error Categories

1. **Permission Errors** - Automation not granted
2. **Not Found Errors** - Task/project lookup failed
3. **Validation Errors** - Invalid dates, empty names
4. **System Errors** - OmniFocus not running, OS errors

### Error Response Format

```javascript
{
  success: false,
  error: {
    code: "PERMISSION_DENIED" | "NOT_FOUND" | "VALIDATION_ERROR" | "SYSTEM_ERROR",
    message: "Human-readable description",
    details: {} // Additional context
  }
}
```

### CLI Error Display

```javascript
// Human-readable errors for CLI users
if (!result.success) {
  console.error(chalk.red(`Error: ${result.error.message}`));
  if (result.error.code === 'PERMISSION_DENIED') {
    console.log(chalk.dim('Run: open "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"'));
  }
  process.exit(1);
}
```

---

## 8. Future Enhancements (Post-MVP / After Basics Working)

### Phase 2 — Advanced Features (After core commands stable)

1. **Perspective Queries** ⭐ High Value
   - `of list --perspective "Today"`
   - `of list --perspective "Forecast"`
   - Unique to OmniFocus — no other CLI has this

2. **Recurring Task Creation**
   - `of create "Weekly review" --repeat weekly --due friday`
   - Options: daily, weekly, monthly, yearly
   - Gap in all existing tools

3. **Sync Status & Control**
   - `of sync --wait` — wait for sync to complete
   - `of sync --status` — check sync state
   - Useful before bulk operations

### Phase 3 — Power User Features (After Phase 2 complete)

4. **Template System**
   - `of template create "meeting" --definition "Meeting with {{Client}} @work ::Meetings //{{Date}}"`
   - `of template use "meeting" --with "Client:Acme,Date:today"`
   - Fast structured capture

5. **Batch Operations**
   - CSV/JSON import/export
   - Bulk creation from file
   - `of import --format csv tasks.csv`

6. **Attachments**
   - Link files in task notes
   - `of attach <task-id> /path/to/file`

7. **Alfred Integration**
   - Workflow for quick capture
   - Packaged separately

8. **Shortcuts App Support**
   - Native iOS/macOS Shortcuts actions
   - For mobile capture

---

## Appendix A: Transport Text Format

OmniFocus supports transport text for quick capture:

```
- Task name @context ::project //due-date #flag
```

**Examples:**
```
- Buy milk @errands ::Shopping //today
- Review PR @work ::Dev //tomorrow 5pm #flag
```

The CLI will generate transport text when `--transport` flag is used.

---

## Appendix B: Date Parsing Reference

Supported natural language formats:

| Input | Parsed As |
|-------|-----------|
| "today" | Today at 23:59 |
| "tomorrow" | Tomorrow at 23:59 |
| "next monday" | Next Monday at 23:59 |
| "+3 days" | 3 days from now |
| "+1 week" | 7 days from now |
| "5pm" | Today at 17:00 |
| "tomorrow 9am" | Tomorrow at 09:00 |
| "2024-12-25" | Specific date |
| "12/25/2024" | Specific date (US format) |

---

## Summary

This CLI design provides:
- ✅ Modern command structure matching OpenClaw patterns
- ✅ Full JSON output for programmatic use
- ✅ Natural language date parsing
- ✅ Transport text support
- ✅ Comprehensive error handling
- ✅ Secure JXA execution
- ✅ Clear path for OpenClaw skill integration
