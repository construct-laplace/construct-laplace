"""MCP server for Construct Laplace (read-only). Lets an AI agent find constructs, papers and measures and cite the original papers.

Local, over stdio:   python server_mcp.py            (LAPLACE_DB=path/to/construct_laplace.sqlite)
Remote, over HTTP:   served at /mcp by server_http.py (streamable HTTP)
Claude Desktop (local):
  {"mcpServers": {"construct-laplace": {"command": "python", "args": ["/path/to/api/server_mcp.py"],
                                          "env": {"LAPLACE_DB": "/path/to/construct_laplace.sqlite"}}}}
"""
from mcp.server.fastmcp import FastMCP
from laplace_query import Laplace

INSTRUCTIONS = (
    'Construct Laplace links constructs, hypothesized relationships, and associated findings across empirical strategy and organization papers in six leading management journals '
    '(SMJ, AMJ, ASQ, Organization Science, Strategy Science and the strategy- and organization-related departments of Management Science, published through September 2026). '
    'The constructs of each paper are linked to a construct dictionary (entryId), in which constructs are related as synonyms, subordinate concepts (type_of) or attributes (aspect_of). Typical flow: search or resolve_construct to get ids, '
    'then construct_relationships, relationship_evidence, construct_measures or find_measures. Answers carry paper ids and hypothesis statements; '
    'cite them. Theory, method and measurement-approach labels were assigned by language models and checked by a second model.')
mcp = FastMCP('construct-laplace', instructions=INSTRUCTIONS, stateless_http=True, json_response=True)
A = Laplace()


@mcp.tool()
def search(query: str, limit: int = 20, journal: str = '', year_from: int = 0, year_to: int = 0, topic: str = '', design: str = '',
           theory: str = '', method: str = '', measurement: str = '', data_type: str = '') -> dict:
    """Full-text search over papers (title, authors, abstract, constructs, hypothesis statements, measures, theory/method/design labels),
    plus the closest constructs in the dictionary. Papers must contain each search word; an exact phrase ranks first. Optional filters as in find_papers."""
    return A.search(query, limit, journal=journal or None, year_from=year_from or None, year_to=year_to or None, topic=topic or None, design=design or None,
                    theory=theory or None, method=method or None, measurement=measurement or None, data_type=data_type or None)


@mcp.tool()
def resolve_construct(name: str, limit: int = 5) -> list:
    """Find constructs in the dictionary for a name as a researcher might write it (synonyms and paper wordings included). Returns entryIds."""
    return A.resolve(name, limit)


@mcp.tool()
def get_entry(entry_id: str) -> dict:
    """Definition, level of analysis, direction convention, broader and narrower constructs, synonyms and paper counts of a construct in the dictionary."""
    return A.entry(entry_id) or {'error': 'entry not found'}


@mcp.tool()
def construct_relationships(entry_id: str, role: str = 'both', scope: str = 'children', min_papers: int = 1, limit: int = 40) -> dict:
    """Predictors and/or outcomes of a construct, counted in papers and split by predicted direction. role: both | predictors | outcomes.
    scope: children (the entry and its narrower entries) | exact."""
    return A.relationships(entry_id, role, scope, min_papers, limit)


@mcp.tool()
def relationship_evidence(source_entry_id: str, target_entry_id: str, scope: str = 'exact', limit: int = 60) -> dict:
    """The hypotheses that test the relationship from source to target: paper, statement, predicted direction, the authors' assessment of empirical support (verdict) and a quotation of the result, plus the papers on each side when supported findings run in both directions."""
    return A.evidence(source_entry_id, target_entry_id, scope, limit)


@mcp.tool()
def construct_measures(entry_id: str, limit: int = 40) -> dict:
    """How papers measured a construct: variable names, descriptions, scales, levels and data sources."""
    return A.measures(entry_id, limit)


@mcp.tool()
def find_measures(query: str = '', approach: str = '', entry_id: str = '', limit: int = 50, offset: int = 0, journal: str = '', year_from: int = 0, year_to: int = 0) -> dict:
    """Measures across papers, to compare how a technique is used. approach: comma-separated codes from list_measurement_approaches
    (e.g. TXT_ML,TXT_DICT for text analysis); query: words in the measure name or description; entry_id: a construct and its narrower entries."""
    return A.find_measures(q=query or None, approach=approach or None, entry=entry_id or None, limit=limit, offset=offset,
                           journal=journal or None, year_from=year_from or None, year_to=year_to or None)


@mcp.tool()
def list_measurement_approaches() -> list:
    """Measurement-approach codes (text analysis variants, survey, rating, experiment, network, patents, media, geographic, archival, other) with counts."""
    return A.measurement_approaches()


@mcp.tool()
def get_paper(paper_id: str) -> dict:
    """One paper in full: metadata, abstract, authors, topics, theories, studies (sample, setting, design, methods), data sources,
    constructs with their links to the construct dictionary, hypotheses with the authors' assessment of empirical support, and measures with their measurement approach."""
    return A.paper_full(paper_id) or {'error': 'paper not found'}


@mcp.tool()
def find_papers(query: str = '', entry_id: str = '', topic: str = '', journal: str = '', year_from: int = 0, year_to: int = 0, design: str = '',
                theory: str = '', method: str = '', measurement: str = '', data_type: str = '', limit: int = 30, offset: int = 0) -> dict:
    """Filtered paper list (newest first, or by relevance with a query). Values: see list_facets. Several values of one filter: comma-separated."""
    return A.find_papers(q=query or None, limit=limit, offset=offset, entry=entry_id or None, topic=topic or None, journal=journal or None,
                         year_from=year_from or None, year_to=year_to or None, design=design or None, theory=theory or None, method=method or None,
                         measurement=measurement or None, data_type=data_type or None)


@mcp.tool()
def list_facets(journal: str = '', year_from: int = 0, year_to: int = 0, topic: str = '') -> dict:
    """Filter values (journals, years, topics, research designs, theories, analysis methods, measurement approaches, data types) with paper counts."""
    return A.facets(journal=journal or None, year_from=year_from or None, year_to=year_to or None, topic=topic or None)


@mcp.tool()
def list_topics() -> list:
    """The 19 paper topics with paper counts."""
    return A.topics()


@mcp.tool()
def find_authors(name: str, limit: int = 20) -> list:
    """Authors by name (printed forms included), with counts of included papers."""
    return A.search_authors(name, limit)


@mcp.tool()
def get_author(person_id: str) -> dict:
    """One author: papers, journals, topics, constructs studied, relationships tested and co-authors."""
    return A.author(person_id) or {'error': 'author not found'}


if __name__ == '__main__':
    mcp.run()
