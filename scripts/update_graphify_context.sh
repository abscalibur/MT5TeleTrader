#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_CANDIDATE="$(cd -- "$SCRIPT_DIR/.." && pwd)"

if git -C "$REPO_CANDIDATE" rev-parse --show-toplevel >/dev/null 2>&1; then
  PROJECT_ROOT="$(git -C "$REPO_CANDIDATE" rev-parse --show-toplevel)"
else
  PROJECT_ROOT="$PWD"
fi

cd "$PROJECT_ROOT"

echo "[graphify] Project root: $PROJECT_ROOT"

if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
else
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[graphify] ERROR: python3 not found and $PROJECT_ROOT/.venv/bin/python is missing." >&2
    exit 1
  fi

  echo "[graphify] Creating local virtual environment at $PROJECT_ROOT/.venv"
  python3 -m venv "$PROJECT_ROOT/.venv"
  PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
fi

GRAPHIFY_BIN="$PROJECT_ROOT/.venv/bin/graphify"
PIP_ARGS=(install "graphifyy[mcp]")

echo "[graphify] Ensuring graphify is installed in the local virtual environment"
"$PYTHON_BIN" -m pip "${PIP_ARGS[@]}"

if [ ! -x "$GRAPHIFY_BIN" ]; then
  echo "[graphify] ERROR: graphify CLI not found at $GRAPHIFY_BIN after installation." >&2
  exit 1
fi

mkdir -p "$PROJECT_ROOT/graphify-out" "$PROJECT_ROOT/obsidian-vault"
printf '%s' "$PYTHON_BIN" > "$PROJECT_ROOT/graphify-out/.graphify_python"

echo "[graphify] Generating graph into $PROJECT_ROOT/graphify-out"
echo "[graphify] Generating Obsidian export into $PROJECT_ROOT/obsidian-vault"
GRAPHIFY_PROJECT_ROOT="$PROJECT_ROOT" "$PYTHON_BIN" - <<'PY'
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.detect import detect, save_manifest
from graphify.export import to_canvas, to_html, to_json, to_obsidian
from graphify.extract import collect_files, extract
from graphify.report import generate

project_root = Path(os.environ["GRAPHIFY_PROJECT_ROOT"]).resolve()
graphify_out = project_root / "graphify-out"
obsidian_dir = project_root / "obsidian-vault"

print(f"[graphify] Detecting files under {project_root}", flush=True)
detection = detect(project_root)

code_files = collect_files(project_root, root=project_root)
if not code_files:
    raise SystemExit("[graphify] ERROR: no supported code files found for AST graph generation.")

print(f"[graphify] Extracting structural graph from {len(code_files)} code files", flush=True)
extraction = extract(code_files, cache_root=project_root)
if not extraction.get("nodes"):
    raise SystemExit("[graphify] ERROR: extraction produced no nodes.")

(graphify_out / ".graphify_detect.json").write_text(json.dumps(detection, indent=2), encoding="utf-8")
(graphify_out / ".graphify_extract.json").write_text(json.dumps(extraction, indent=2), encoding="utf-8")

G = build_from_json(extraction)
communities = cluster(G)
cohesion = score_all(G, communities)
gods = god_nodes(G)
surprises = surprising_connections(G, communities)

def pick_label(cid: int, members: list[str]) -> str:
    ranked = []
    fallback = []
    for node_id in members:
        data = G.nodes[node_id]
        label = str(data.get("label", node_id)).strip()
        deg = G.degree(node_id)
        fallback.append((deg, label))
        if any(token in label for token in ("/", "\\")) or label.endswith((".py", ".md", ".json", ".yaml", ".yml", ".ini", ".sh")):
            continue
        ranked.append((deg, label))
    ranked = sorted(ranked or fallback, key=lambda item: (-item[0], item[1].lower()))
    picked = [label for _, label in ranked[:2] if label]
    if not picked:
        return f"Community {cid}"
    joined = " / ".join(picked)
    return joined[:80]

labels = {cid: pick_label(cid, members) for cid, members in communities.items()}
questions = suggest_questions(G, communities, labels)

report = generate(
    G,
    communities,
    cohesion,
    labels,
    gods,
    surprises,
    detection,
    {"input": extraction.get("input_tokens", 0), "output": extraction.get("output_tokens", 0)},
    str(project_root),
    suggested_questions=questions,
)

(graphify_out / ".graphify_analysis.json").write_text(
    json.dumps(
        {
            "communities": {str(k): v for k, v in communities.items()},
            "cohesion": {str(k): v for k, v in cohesion.items()},
            "gods": gods,
            "surprises": surprises,
            "questions": questions,
        },
        indent=2,
    ),
    encoding="utf-8",
)
(graphify_out / ".graphify_labels.json").write_text(
    json.dumps({str(k): v for k, v in labels.items()}, indent=2),
    encoding="utf-8",
)
(graphify_out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
to_json(G, communities, str(graphify_out / "graph.json"))
to_html(G, communities, str(graphify_out / "graph.html"), community_labels=labels)
to_obsidian(G, communities, str(obsidian_dir), community_labels=labels, cohesion=cohesion)
to_canvas(G, communities, str(obsidian_dir / "graph.canvas"), community_labels=labels)

save_manifest(detection["files"], manifest_path=str(graphify_out / "manifest.json"))

cost_path = graphify_out / "cost.json"
if cost_path.exists():
    try:
        cost = json.loads(cost_path.read_text(encoding="utf-8"))
    except Exception:
        cost = {"runs": [], "total_input_tokens": 0, "total_output_tokens": 0}
else:
    cost = {"runs": [], "total_input_tokens": 0, "total_output_tokens": 0}
cost["runs"].append({
    "date": datetime.now(UTC).isoformat(),
    "input_tokens": extraction.get("input_tokens", 0),
    "output_tokens": extraction.get("output_tokens", 0),
    "files": detection.get("total_files", 0),
    "mode": "local-ast",
})
cost["total_input_tokens"] += extraction.get("input_tokens", 0)
cost["total_output_tokens"] += extraction.get("output_tokens", 0)
cost_path.write_text(json.dumps(cost, indent=2), encoding="utf-8")

print(
    f"[graphify] Graph complete: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities",
    flush=True,
)
PY

echo "[graphify] Attempting local OpenCode plugin install"
OPENCODE_JSON_PREEXISTED=0
if [ -f "$PROJECT_ROOT/opencode.json" ]; then
  OPENCODE_JSON_PREEXISTED=1
fi

if "$GRAPHIFY_BIN" opencode install; then
  echo "[graphify] OpenCode plugin install completed"
else
  echo "[graphify] WARNING: 'graphify opencode install' failed; continuing with local repository setup." >&2
fi

if [ "$OPENCODE_JSON_PREEXISTED" -eq 0 ] && [ -f "$PROJECT_ROOT/opencode.json" ] && [ -f "$PROJECT_ROOT/opencode.jsonc" ]; then
  echo "[graphify] Removing generated $PROJECT_ROOT/opencode.json in favor of project-local opencode.jsonc"
  rm -f "$PROJECT_ROOT/opencode.json"
fi

echo "[graphify] Done"

