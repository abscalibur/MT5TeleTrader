## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)

# Local Project Knowledge Rules

This repository has a local OpenCode + Graphify + Obsidian setup.

Use Graphify before broad code search.

When asked about architecture, dependencies, flows, call chains, services, modules, or where logic lives:
1. Read `graphify-out/GRAPH_REPORT.md` if it exists.
2. Use the `graphify-local` MCP server.
3. Prefer Graphify graph queries before grep/raw file search.
4. Inspect raw files only after using the graph context.

Use the Obsidian MCP only for this project vault:
- Vault path: `./obsidian-vault`
- Do not write notes outside this local vault.
- Use Obsidian wiki links where helpful.
- Prefer appending dated notes over overwriting existing notes.

After meaningful code changes:
1. Run `./scripts/update_graphify_context.sh`
2. Summarize architectural changes into `./obsidian-vault`

Do not use global Obsidian vaults for this project.
Do not modify global OpenCode config.

