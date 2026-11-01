# Query API and MCP server

The server gives read-only access to `data/construct_laplace.sqlite`. It does not run a language model. A researcher's AI agent calls the tools and writes its answer from the records it retrieves.

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

- `laplace_query.py`: the query layer (class `Laplace`). `atlas_query.py` is an older name kept for older scripts.
- `server_mcp.py`: the MCP tools. `server_http.py`: the REST endpoints and the MCP endpoint; `/` lists them with examples and `/openapi.json` describes them.
- `entry_emb.npy`: optional vectors for construct name lookup, used only when `fastembed` is installed.

| HTTP | MCP tool | Returns |
|---|---|---|
| `GET /search?q=` (+ filters) | `search` | Papers that contain the search words, and the closest constructs in the dictionary |
| `GET /resolve?q=` | `resolve_construct` | Constructs in the dictionary that match a name, synonym, paper wording, or measure name |
| `GET /entries/{id}` | `get_entry` | Definition, level of analysis, direction convention, broader and narrower constructs, synonyms |
| `GET /entries/{id}/relationships` | `construct_relationships` | Predictors and outcomes, counted in papers and split by predicted direction |
| `GET /evidence?source=&target=` | `relationship_evidence` | The hypotheses that test the relationship, with paper, statement, the authors' assessment of empirical support, and a quotation of the result |
| `GET /entries/{id}/measures` | `construct_measures` | How papers measured the construct |
| `GET /measures` (+ filters) | `find_measures` | Measures across papers by approach, construct or words |
| `GET /measurement-approaches` | `list_measurement_approaches` | The 12 approach codes |
| `GET /papers` (+ filters) | `find_papers` | Filtered paper list |
| `GET /papers/{id}` | `get_paper` | One paper in full |
| `GET /facets` | `list_facets` | Filter values with paper counts |
| `GET /topics` | `list_topics` | The 19 topics |
| `GET /authors`, `GET /authors/{id}` | `find_authors`, `get_author` | Authors and their papers |
