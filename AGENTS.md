# Compliance_Gap_Analyser — Project Knowledge Base

## OVERVIEW

Scaffold project for a Compliance Gap Analyser tool. No source code yet — only AI/LLM tooling configuration and code-review-graph MCP integration.

## STRUCTURE

```
./
├── .claude/skills/    # 4 Claude-specific skills (review, refactor, explore, debug)
├── .code-review-graph/  # Auto-generated knowledge graph (gitignored)
├── .kiro/steering/    # Kiro IDE steering config
├── .mcp.json          # MCP server config (code-review-graph)
└── .opencode.json     # OpenCode MCP server config (duplicate of .mcp.json)
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| MCP tools | `.mcp.json`, `.opencode.json` | Both configure `code-review-graph` |
| Claude skills | `.claude/skills/*.md` | review-changes, refactor-safely, explore-codebase, debug-issue |
| Graph hooks | `.claude/settings.json` | Post-edit auto-update, session-start status check |
| Graph DB | `.code-review-graph/graph.db` | Auto-generated, gitignored |

## CONVENTIONS

- **MCP-first exploration**: Use `code-review-graph` tools (semantic_search_nodes, query_graph, detect_changes) before Grep/Glob/Read
- **Token efficiency**: All skills enforce `detail_level="minimal"`, target ≤5 tool calls and ≤800 output tokens per task
- **Graph auto-update**: `code-review-graph update --skip-flows` runs on every Edit/Write/Bash via Claude hooks
- **No Python code yet**: When code is added, expect standard Python project structure (pyproject.toml, src/ or flat, tests/)

## ANTI-PATTERNS

- **6 files are identical duplicates** (38 lines each): `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursorrules`, `.windsurfrules`, `.kiro/steering/code-review-graph.md` — consolidate to one source
- **`.code-review-graph/` contains `*` in `.gitignore`** — the glob ignores everything including the `.gitignore` itself; graph.db won't be tracked

## NOTES

- Project name implies Python compliance analysis tool, but no source files exist
- When source code is added, create `pyproject.toml`, `src/`, `tests/` structure
- Consider consolidating the 6 duplicate AI-tool config files into a single canonical source
