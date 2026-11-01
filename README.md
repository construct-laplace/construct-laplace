# Construct Laplace

Construct Laplace is an AI-enabled research infrastructure that links tested hypotheses and their underlying constructs across empirical papers published in six leading journals (*Strategic Management Journal*, *Academy of Management Journal*, *Administrative Science Quarterly*, *Organization Science*, *Strategy Science*, and *Management Science*) into a queryable knowledge network. The current release covers 4,784 papers published from 1959 through September 2026, with 24,566 hypotheses involving 2,052 conceptually distinct constructs.

For each hypothesis, the database records the role of its constructs as predictors, outcomes, moderators, or mediators, the predicted direction, the definitions and measures of each construct, the data and setting of the study, and the authors' assessment of whether the hypothesis is supported. A construct dictionary links constructs across papers through synonyms, subordinate concepts, and attributes, so that researchers can compare studies of the same relationship.

The website is at https://construct-laplace.org. Journal reviewers can enter without an account by choosing "I'm a journal reviewer, enter anonymously" on the sign-in page; the Use with AI page then gives them a free API key for connecting their own AI agents. Other researchers sign in free with Google or email. This repository contains the same data as the website, together with the query API and the Model Context Protocol (MCP) server through which AI agents access it. The proposal and its technical appendix describe each step of the procedure.

## What this repository contains

| File or folder | What it is |
|---|---|
| `README.md` | This file |
| `DATA_GUIDE.md` | Descriptions of the tables and columns in the database |
| `setup.py` | Unpacks the database (needs no extra packages) |
| `data/construct_laplace.sqlite.xz` | The full database, compressed (17 MB; about 90 MB unpacked). Same release as the website |
| `data/csv/` | Spreadsheet copies of the main tables, limited to the 4,784 included papers: `papers`, `hypotheses`, `constructs`, `measures`, `entries` (the construct dictionary), `evidence_links` and `moderator_links` (hypotheses linked to constructs in the dictionary), and `entry_edges` (tested hypotheses per pair of constructs) |
| `data/article_ledger.csv` | The 28,193 articles published in the six journals through September 2026, each with the reason it was included or excluded |
| `data/exclusion_codes.csv` | What each exclusion code means and how many articles it covers |
| `api/` | A REST API and an MCP server through which researchers' AI agents search the data and link their answers to the original papers. The server itself does not run a language model. See `api/README.md` |

**Not included:** PDFs and full texts of the papers (they are copyrighted), raw model outputs, and the code of the website. Short quotations of the reported results are kept so that records can be checked against the original papers.

## How to use it

**1. Use the website.** Search by construct, paper, author, or topic, and compare studies that test the same relationship.

**2. Open the data.** Python 3.8 or later.

```bash
python3 setup.py                          # unpack the database to data/construct_laplace.sqlite
```

Then open `data/construct_laplace.sqlite` with a SQLite tool, or the CSV files with a spreadsheet, R or Python. `DATA_GUIDE.md` explains each column.

**3. Connect an AI agent.**

```bash
pip install "mcp>=1.27,<2" uvicorn numpy scikit-learn
cd api && LAPLACE_DB=../data/construct_laplace.sqlite uvicorn server_http:app --port 8000
```

`http://localhost:8000/` lists the endpoints. An AI agent connects to `http://localhost:8000/mcp`, or starts `api/server_mcp.py` itself over stdio (setup for Claude Desktop and Claude Code in `api/README.md`).

## Notes

- Abstracts come from bibliographic databases. Author names are those printed in the papers; no institutions are stored.
- The data are for research use.
