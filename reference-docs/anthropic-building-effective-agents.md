# Anthropic: Building Effective AI Agents

> **Source:** https://www.anthropic.com/engineering/building-effective-agents  
> **Retrieved:** 2026-02-14  
> **Purpose:** Official Anthropic best practices for building LLM agents

---

## What are agents?

**Agentic systems** include both workflows and agents:

- **Workflows:** Systems where LLMs and tools are orchestrated through predefined code paths
- **Agents:** Systems where LLMs dynamically direct their own processes and tool usage, maintaining control over how they accomplish tasks

---

## When (and when not) to use agents

**Recommendation:** Find the simplest solution possible, only increasing complexity when needed.

- Agentic systems trade latency and cost for better task performance
- Optimize single LLM calls with retrieval and in-context examples first
- Use workflows for predictability and consistency
- Use agents when flexibility and model-driven decision-making are needed at scale

---

## When and how to use frameworks

Popular frameworks:
- Claude Agent SDK
- Strands Agents SDK by AWS
- Rivet (drag and drop GUI)
- Vellum (GUI tool)

**Recommendation:** Start by using LLM APIs directly. Many patterns can be implemented in a few lines of code. If using a framework, ensure you understand the underlying code.

---

## Building Blocks, Workflows, and Agents

### Building Block: The Augmented LLM

The basic building block is an LLM enhanced with:
- Retrieval
- Tools
- Memory

Focus on:
1. Tailoring these capabilities to your specific use case
2. Ensuring they provide an easy, well-documented interface

Consider using the Model Context Protocol (MCP) for third-party tool integration.

---

## Workflow Patterns

### 1. Prompt Chaining

Decompose a task into a sequence of steps, where each LLM call processes the output of the previous one.

**When to use:** Task can be easily decomposed into fixed subtasks. Trade latency for higher accuracy.

**Examples:**
- Generate marketing copy, then translate it
- Write outline → check criteria → write document

### 2. Routing

Classify an input and direct it to a specialized followup task.

**When to use:** Complex tasks with distinct categories better handled separately.

**Examples:**
- Route customer service queries (general, refund, technical)
- Route easy questions to Haiku, hard questions to Sonnet

### 3. Parallelization

LLMs work simultaneously on a task; outputs aggregated programmatically.

**Variations:**
- **Sectioning:** Break task into independent subtasks run in parallel
- **Voting:** Run same task multiple times for diverse outputs

**When to use:** Subtasks can be parallelized for speed, or multiple perspectives needed for confidence.

**Examples:**
- Guardrails: one model processes queries, another screens for inappropriate content
- Code vulnerability reviews by multiple prompts
- Content moderation with different vote thresholds

### 4. Orchestrator-Workers

Central LLM dynamically breaks down tasks, delegates to worker LLMs, synthesizes results.

**When to use:** Complex tasks where you can't predict subtasks needed (e.g., coding with multiple file changes).

**Key difference from parallelization:** Subtasks aren't pre-defined; determined by orchestrator.

### 5. Evaluator-Optimizer

One LLM generates response; another provides evaluation and feedback in a loop.

**When to use:** Clear evaluation criteria and iterative refinement provides measurable value.

**Examples:**
- Literary translation with evaluator critiques
- Complex search with evaluator deciding on further searches

---

## Agents

Agents operate independently, potentially returning to human for information or judgment. They gain "ground truth" from environment at each step (tool results, code execution).

**When to use:** Open-ended problems where you can't predict required steps. Must have trust in model's decision-making.

**Characteristics:**
- Higher costs
- Potential for compounding errors
- Need extensive sandboxed testing
- Appropriate guardrails required

**Examples:**
- Coding agent for SWE-bench tasks
- "Computer use" reference implementation

---

## Combining and Customizing Patterns

These patterns aren't prescriptive. Developers can shape and combine them.

**Key principle:** Measure performance and iterate. Only add complexity when it demonstrably improves outcomes.

---

## Summary: Core Principles

When implementing agents, follow three principles:

1. **Maintain simplicity** in your agent's design
2. **Prioritize transparency** by explicitly showing the agent's planning steps
3. **Carefully craft your agent-computer interface (ACI)** through thorough tool documentation and testing

Don't hesitate to reduce abstraction layers and build with basic components as you move to production.

---

## Appendix 1: Agents in Practice

### Customer Support

Natural fit for agents because:
- Follows conversation flow with external information access
- Tools can pull customer data, order history, knowledge base
- Actions (refunds, ticket updates) handled programmatically
- Success clearly measured through user-defined resolutions

### Coding Agents

Effective because:
- Code solutions verifiable through automated tests
- Agents can iterate using test results as feedback
- Problem space well-defined and structured
- Output quality measured objectively

**Important:** Human review remains crucial for ensuring solutions align with broader system requirements.

---

## Appendix 2: Prompt Engineering Your Tools

Tool definitions should get as much attention as overall prompts.

### Format Guidelines

- Give the model enough tokens to "think" before writing itself into a corner
- Keep format close to what model has seen naturally in text
- Avoid formatting overhead (accurate line counts, string escaping)

### Agent-Computer Interface (ACI) Best Practices

1. **Put yourself in the model's shoes:** Is tool usage obvious from description?
2. **Improve parameter names/descriptions:** Like writing a great docstring
3. **Test tool usage:** Run many examples in workbench to see mistakes
4. **Poka-yoke your tools:** Change arguments to make mistakes harder

**Real example:** Found that model made mistakes with relative filepaths after agent moved from root. Fixed by requiring absolute filepaths.

---

## Key Takeaways for Configuration Review

1. **Prefer simple patterns** over complex frameworks
2. **Use workflows** for predictable, well-defined tasks
3. **Use agents** only for open-ended problems requiring flexibility
4. **Design clear tool interfaces** with good documentation
5. **Test extensively** before production deployment
6. **Show planning steps** for transparency
7. **Iterate based on measurements**, not assumptions
