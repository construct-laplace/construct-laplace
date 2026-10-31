# Construct Laplace: research artifact

Construct Laplace records the tested content of empirical strategy and organization research at the level of the formal hypothesis. For every hypothesis stated and tested in the papers in scope of six journals (*Strategic Management Journal*, *Academy of Management Journal*, *Administrative Science Quarterly*, *Organization Science*, *Strategy Science* and three departments of *Management Science*), it records the constructs, their definitions and measures, the predicted direction and the result the authors report. Paper constructs are filed under a shared concept dictionary, so findings reported under different names can be compared.

The web explorer is online at https://construct-laplace.org (free sign-in with Google or email). This repository holds the same data as the website, and the query API and MCP server that let AI agents use it. The proposal and the technical appendix describe the design and each procedure.

## What this repository contains

| File or folder | What it is |
|---|---|
| `README.md` | This file |
| `DATA_GUIDE.md` | Every table and column of the database, in plain words |
| `setup.py` | Unpacks the database (needs no extra packages) |
| `data/construct_laplace.sqlite.xz` | The full database, compressed (17 MB; about 90 MB unpacked). Same release as the website |
| `data/csv/` | Spreadsheet copies of the main tables, limited to the 4,784 papers in scope: `papers`, `hypotheses`, `constructs`, `measures`, `entries` (the concept dictionary), `evidence_links` and `moderator_links` (hypotheses linked to dictionary entries), and `entry_edges` (evidence per pair of concepts) |
| `data/article_ledger.csv` | All 28,193 articles published in the six journals, each with its status and the reason it was included or excluded |
| `data/exclusion_codes.csv` | What each exclusion code means and how many articles it covers |
| `api/` | The query layer, a REST API and an MCP server (Model Context Protocol), so an AI agent can query the data and cite each hypothesis it uses. No language model runs here. See `api/README.md` |

**Not included:** PDFs and full texts of the papers (they are copyrighted), raw model outputs, and the code of the website. Short quotes from the papers are kept so each record can be checked.

## How to use it

**1. Browse.** Use the website. Search a construct, open a paper, or follow a relationship to the hypotheses behind it.

**2. Open the data.** Python 3.8 or later.

```bash
python3 setup.py                          # unpack the database to data/construct_laplace.sqlite
```

Then open `data/construct_laplace.sqlite` with any SQLite tool, or the CSV files with a spreadsheet, R or Python. `DATA_GUIDE.md` explains each column.

**3. Connect an AI agent.**

```bash
pip install "mcp>=1.27,<2" uvicorn numpy scikit-learn
cd api && LAPLACE_DB=../data/construct_laplace.sqlite uvicorn server_http:app --port 8000
```

`http://localhost:8000/` lists the endpoints. An AI agent connects to `http://localhost:8000/mcp`, or starts `api/server_mcp.py` itself over stdio (setup for Claude Desktop and Claude Code in `api/README.md`).

## Notes

- Abstracts come from bibliographic databases. Author names are those printed in the papers; no institutions are stored.
- The data are for research use.
