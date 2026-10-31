# Query API and MCP server

Read-only access to `data/construct_laplace.sqlite`. No language model runs here; an AI agent calls the tools and composes its answer from the records it gets back.

```bash
pip install "mcp>=1.27,<2" uvicorn numpy scikit-learn
cd api
LAPLACE_DB=../data/construct_laplace.sqlite uvicorn server_http:app --port 8000   # REST API, and MCP over HTTP at /mcp
LAPLACE_DB=../data/construct_laplace.sqlite python3 server_mcp.py                 # MCP over stdio
```

Claude Desktop (stdio), in `claude_desktop_config.json`:

```json
{"mcpServers": {"construct-laplace": {"command": "python3", "args": ["/full/path/api/server_mcp.py"],
  "env": {"LAPLACE_DB": "/full/path/data/construct_laplace.sqlite"}}}}
```

Claude Code, with the HTTP server running: `claude mcp add --transport http construct-laplace http://localhost:8000/mcp`

- `laplace_query.py`: the query layer (class `Laplace`). `atlas_query.py` is an older name kept as a shim.
- `server_mcp.py`: the MCP tools. `server_http.py`: the REST endpoints and the MCP endpoint; `/` lists them with examples and `/openapi.json` describes them.
- `entry_emb.npy`: optional vectors for construct name lookup, used only when `fastembed` is installed.

| HTTP | MCP tool | Returns |
|---|---|---|
| `GET /search?q=` (+ filters) | `search` | Papers matching every word, and the best dictionary entries |
| `GET /resolve?q=` | `resolve_construct` | Dictionary entries for a construct name, alias, paper wording or measure name |
| `GET /entries/{id}` | `get_entry` | Definition, level, sign convention, place in the tree, aliases |
| `GET /entries/{id}/relationships` | `construct_relationships` | Predictors and outcomes, counted in papers, split by sign |
| `GET /evidence?source=&target=` | `relationship_evidence` | Every hypothesis on the link, with paper, statement, verdict and quote |
| `GET /entries/{id}/measures` | `construct_measures` | How papers measured the construct |
| `GET /measures` (+ filters) | `find_measures` | Measures across papers by approach, construct or words |
| `GET /measurement-approaches` | `list_measurement_approaches` | The 12 approach codes |
| `GET /papers` (+ filters) | `find_papers` | Filtered paper list |
| `GET /papers/{id}` | `get_paper` | One paper in full |
| `GET /facets` | `list_facets` | Every filter value with paper counts |
| `GET /topics` | `list_topics` | The 19 topics |
| `GET /authors`, `GET /authors/{id}` | `find_authors`, `get_author` | Authors and their papers |
