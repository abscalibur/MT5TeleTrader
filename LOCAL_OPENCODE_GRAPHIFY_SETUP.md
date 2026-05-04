# Local OpenCode + Graphify Setup

This repository is configured with a **project-local** Graphify + Obsidian + OpenCode setup. Nothing in the global OpenCode config was required.

## Files created or updated

- `.venv/` — local Python virtual environment with `graphifyy[mcp]`
- `.graphifyignore` — Graphify ignore rules for this repo
- `.gitignore` — local ignores for `.venv/`, `graphify-out/`, and `obsidian-vault/`
- `graphify-out/` — generated graph outputs
  - `graphify-out/graph.json`
  - `graphify-out/GRAPH_REPORT.md`
  - `graphify-out/graph.html`
- `obsidian-vault/` — local Obsidian export for this project only
- `.opencode/plugins/graphify.js` — local Graphify OpenCode plugin
- `opencode.jsonc` — project-local OpenCode config with MCP servers
- `AGENTS.md` — local OpenCode/Graphify/Obsidian instructions for this repo
- `scripts/update_graphify_context.sh` — helper script to regenerate the graph and vault

## Regenerate or update the graph

Run:

```bash
./scripts/update_graphify_context.sh
```

This will:

1. Use `./.venv/`
2. Ensure `graphifyy[mcp]` is installed locally
3. Rebuild `graphify-out/`
4. Rebuild `obsidian-vault/`
5. Re-apply the local Graphify OpenCode plugin if supported

## Start OpenCode from this project

From this repository root, run:

```bash
opencode
```

Because `opencode.jsonc` is in this project root, OpenCode should pick up the local MCP configuration and instructions when started here.

## Test the Graphify MCP

Start OpenCode from this project root, then try:

```text
Use graphify-local to explain the main architecture of this repo.
```

You can also confirm the local Graphify MCP command path from `opencode.jsonc`:

- Python: `/Users/abscalibur/metaauto/.venv/bin/python`
- Graph file: `/Users/abscalibur/metaauto/graphify-out/graph.json`

## Test the Obsidian MCP

Start OpenCode from this project root, then try:

```text
Search obsidian-local for project notes and summarize them.
```

And:

```text
Create an Obsidian note in the local vault summarizing this repo architecture.
```

The local vault path is:

- `/Users/abscalibur/metaauto/obsidian-vault`

## Example prompts

```text
Use graphify-local to explain the main architecture of this repo.
```

```text
Search obsidian-local for project notes and summarize them.
```

```text
Create an Obsidian note in the local vault summarizing this repo architecture.
```

## Notes

- The OpenCode MCP command arrays in `opencode.jsonc` use absolute paths for this project.
- The Graphify OpenCode plugin is stored locally under `.opencode/plugins/`.
- This setup is scoped to this repository only.

