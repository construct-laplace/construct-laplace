"""Construct Laplace HTTP API (read-only) with the MCP server mounted at /mcp.

Run:  LAPLACE_DB=path/to/construct_laplace.sqlite uvicorn server_http:app --host 0.0.0.0 --port 8000
Needs only: mcp (brings starlette, uvicorn, pydantic), numpy, scikit-learn.
"""
import contextlib, json, os
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route
from server_mcp import mcp, A

VERSION = '5.0'
PUBLIC_URL = os.environ.get('LAPLACE_PUBLIC_URL', '')

# ---------- parameter helpers ----------
FILTERS = ['journal', 'year_from', 'year_to', 'topic', 'design', 'theory', 'method', 'measurement', 'data_type']


def _i(v, d=None, lo=None, hi=None):
    try: x = int(v)
    except (TypeError, ValueError): return d
    if lo is not None: x = max(lo, x)
    if hi is not None: x = min(hi, x)
    return x


def _filters(qp):
    f = {k: (qp.get(k) or None) for k in FILTERS}
    f['year_from'], f['year_to'] = _i(f['year_from']), _i(f['year_to'])
    return f


def _ok(x, what='item'):
    if x is None: return JSONResponse({'error': f'{what} not found'}, status_code=404)
    return JSONResponse(x)


# ---------- endpoints (name, path, handler, summary, params) ----------
async def search(r: Request):
    q = r.query_params.get('q', '')
    return JSONResponse(A.search(q, _i(r.query_params.get('limit'), 20, 1, 200), **_filters(r.query_params)))


async def resolve(r: Request):
    return JSONResponse(A.resolve(r.query_params.get('q', ''), _i(r.query_params.get('limit'), 5, 1, 25)))


async def entry(r: Request):
    return _ok(A.entry(r.path_params['entry_id']), 'entry')


async def relationships(r: Request):
    e = r.path_params['entry_id']
    if e not in A.E: return _ok(None, 'entry')
    qp = r.query_params
    role = qp.get('role', 'both') if qp.get('role') in ('both', 'predictors', 'outcomes') else 'both'
    scope = qp.get('scope', 'children') if qp.get('scope') in ('exact', 'children') else 'children'
    return JSONResponse(A.relationships(e, role, scope, _i(qp.get('min_papers'), 1, 1), _i(qp.get('limit'), 50, 1, 500)))


async def evidence(r: Request):
    qp = r.query_params; s, t = qp.get('source'), qp.get('target')
    if s not in A.E or t not in A.E: return JSONResponse({'error': 'source and target must be entry ids (see /resolve)'}, status_code=400)
    scope = qp.get('scope', 'exact') if qp.get('scope') in ('exact', 'children') else 'exact'
    return JSONResponse(A.evidence(s, t, scope, _i(qp.get('limit'), 100, 1, 1000)))


async def entry_measures(r: Request):
    e = r.path_params['entry_id']
    if e not in A.E: return _ok(None, 'entry')
    return JSONResponse(A.measures(e, _i(r.query_params.get('limit'), 50, 1, 1000)))


async def measures(r: Request):
    qp = r.query_params
    return JSONResponse(A.find_measures(q=qp.get('q') or None, approach=qp.get('approach') or None, entry=qp.get('entry') or None,
                                        limit=_i(qp.get('limit'), 50, 1, 500), offset=_i(qp.get('offset'), 0, 0), **_filters(qp)))


async def approaches(r: Request):
    return JSONResponse(A.measurement_approaches())


async def papers(r: Request):
    qp = r.query_params
    return JSONResponse(A.find_papers(q=qp.get('q') or None, limit=_i(qp.get('limit'), 50, 1, 500), offset=_i(qp.get('offset'), 0, 0),
                                      entry=qp.get('entry') or None, **_filters(qp)))


async def paper(r: Request):
    return _ok(A.paper_full(r.path_params['paper_id']), 'paper')


async def facets(r: Request):
    return JSONResponse(A.facets(**_filters(r.query_params)))


async def topics(r: Request):
    return JSONResponse(A.topics())


async def authors(r: Request):
    return JSONResponse(A.search_authors(r.query_params.get('q', ''), _i(r.query_params.get('limit'), 20, 1, 200)))


async def author(r: Request):
    return _ok(A.author(r.path_params['person_id']), 'author')


async def health(r: Request):
    return JSONResponse({'ok': True, 'version': VERSION, 'papers': len(A.P), 'entries': len(A.E)})


P = lambda name, where='query', typ='string', desc='', req=False, enum=None: {'name': name, 'in': where, 'required': req or where == 'path', 'description': desc,
                                                                              'schema': {'type': typ, **({'enum': enum} if enum else {})}}
FP = [P('journal', desc='Journal name or short code (SMJ, AMJ, ASQ, MS, OS, SS)'), P('year_from', typ='integer'), P('year_to', typ='integer'),
      P('topic', desc='Topic id (T01..T19), see /topics'), P('design', desc='Research design, e.g. panel, experiment; comma-separated for several'),
      P('theory', desc='Theory label, e.g. Resource-based view (see /facets)'), P('method', desc='Analysis method label (see /facets)'),
      P('measurement', desc='Measurement-approach code(s), e.g. TXT_ML,TXT_DICT (see /measurement-approaches)'),
      P('data_type', desc='commercial_database, government_administrative, archival_documents, authors_survey, public_database, interviews, experiment, field_observation')]
LIM = [P('limit', typ='integer'), P('offset', typ='integer')]
ENDPOINTS = [
    ('search', '/search', search, 'Search papers and constructs', 'Full-text search over papers (title, authors, abstract, constructs, hypotheses, measures, labels) plus the best-matching dictionary entries. Every word must appear; an exact phrase ranks first.', [P('q', desc='Query', req=True), P('limit', typ='integer')] + FP),
    ('resolve', '/resolve', resolve, 'Resolve a construct name', 'Dictionary entries for a construct name, alias, paper wording or measure name.', [P('q', req=True), P('limit', typ='integer')]),
    ('entry', '/entries/{entry_id}', entry, 'Dictionary entry', 'Definition, level, sign convention, tree path, narrower entries, aliases, coverage.', [P('entry_id', 'path')]),
    ('relationships', '/entries/{entry_id}/relationships', relationships, 'Predictors and outcomes', 'Relationships of an entry, counted in papers and split by sign.', [P('entry_id', 'path'), P('role', enum=['both', 'predictors', 'outcomes']), P('scope', enum=['children', 'exact']), P('min_papers', typ='integer'), P('limit', typ='integer')]),
    ('entry_measures', '/entries/{entry_id}/measures', entry_measures, 'How a construct was measured', 'Measures used for an entry across papers.', [P('entry_id', 'path'), P('limit', typ='integer')]),
    ('evidence', '/evidence', evidence, 'Evidence for one relationship', 'Every hypothesis linking source to target, with statement, verdict and quote.', [P('source', req=True), P('target', req=True), P('scope', enum=['exact', 'children']), P('limit', typ='integer')]),
    ('measures', '/measures', measures, 'Measures across papers', 'Compare how a technique or construct is measured across papers: filter by measurement approach, entry and words.', [P('q'), P('approach', desc='Codes, e.g. TXT_ML,TXT_DICT'), P('entry')] + LIM + FP),
    ('approaches', '/measurement-approaches', approaches, 'Measurement approaches', 'Codes with what they cover and counts of measures and papers.', []),
    ('papers', '/papers', papers, 'Filtered paper list', 'Papers by filters, newest first, or by relevance with q.', [P('q'), P('entry')] + LIM + FP),
    ('paper', '/papers/{paper_id}', paper, 'One paper in full', 'Metadata, abstract, authors, topics, theories, studies, data sources, constructs, hypotheses, measures.', [P('paper_id', 'path')]),
    ('facets', '/facets', facets, 'Filter values with counts', 'Journals, years, topics, designs, theories, methods, measurement approaches and data types, with paper counts under the given filters.', FP),
    ('topics', '/topics', topics, 'Topics', 'The 19 topics with paper counts.', []),
    ('authors', '/authors', authors, 'Find authors', 'Authors by name with in-scope paper counts.', [P('q', req=True), P('limit', typ='integer')]),
    ('author', '/authors/{person_id}', author, 'One author', 'Papers, journals, topics, constructs, relationships and co-authors.', [P('person_id', 'path')]),
    ('health', '/health', health, 'Health', 'Service status and counts.', []),
]


def openapi(r: Request):
    base = PUBLIC_URL or str(r.base_url).rstrip('/')
    spec = {'openapi': '3.1.0', 'info': {'title': 'Construct Laplace API', 'version': VERSION,
            'description': 'Read-only access to Construct Laplace: formal hypotheses from empirical strategy and organization papers, their constructs mapped to a dictionary, and the evidence linking them. The MCP server is at /mcp (streamable HTTP).'},
            'servers': [{'url': base}], 'paths': {}}
    for name, path, _, summary, desc, params in ENDPOINTS:
        spec['paths'][path] = {'get': {'operationId': name, 'summary': summary, 'description': desc, 'parameters': params,
                                        'responses': {'200': {'description': 'JSON', 'content': {'application/json': {}}}}}}
    return JSONResponse(spec)


def home(r: Request):
    base = PUBLIC_URL or str(r.base_url).rstrip('/')
    rows = ''.join(f'<tr><td><code>GET {p}</code></td><td>{d}</td></tr>' for _, p, _, s, d, _ in ENDPOINTS)
    return HTMLResponse(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Construct Laplace API</title><style>body{{font:15px/1.5 system-ui,sans-serif;max-width:860px;margin:32px auto;padding:0 16px;color:#1d1d1f}}
code,pre{{font:13px ui-monospace,monospace;background:#f3f3f1;border-radius:4px}}code{{padding:1px 4px}}pre{{padding:10px;overflow:auto}}
table{{border-collapse:collapse;width:100%}}td{{border-top:1px solid #e5e5e2;padding:6px 8px;vertical-align:top}}h1{{font-size:24px}}h2{{font-size:17px;margin-top:26px}}</style></head><body>
<h1>Construct Laplace API</h1>
<p>{len(A.P):,} empirical strategy and organization papers with separately stated and tested hypotheses, {len(A.E):,} dictionary constructs and the evidence linking them. Read-only, JSON, no key needed.</p>
<h2>Try it</h2><pre>curl "{base}/search?q=text%20analysis&amp;limit=5"
curl "{base}/measures?approach=TXT_ML,TXT_DICT&amp;limit=20"
curl "{base}/papers?design=experiment&amp;journal=SMJ&amp;year_from=2015"</pre>
<h2>Use it from an AI assistant (MCP)</h2><p>Add a remote MCP server with the URL <code>{base}/mcp</code>. In Claude: Settings, Connectors, Add custom connector. For clients that only run local servers: <code>npx mcp-remote {base}/mcp</code>.</p>
<h2>Endpoints</h2><table>{rows}</table>
<p>Machine-readable description: <a href="/openapi.json">/openapi.json</a>. Theory, method and measurement-approach labels were assigned by language models and checked by a second model.</p>
</body></html>''')


@contextlib.asynccontextmanager
async def lifespan(app):
    async with mcp.session_manager.run():
        yield


# a public read-only service: accept any Host header (the default only allows localhost)
from mcp.server.transport_security import TransportSecuritySettings
mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
mcp_app = mcp.streamable_http_app()      # route /mcp
routes = [Route('/', home), Route('/docs', home), Route('/openapi.json', openapi)] + [Route(p, h, name=n) for n, p, h, *_ in ENDPOINTS] + list(mcp_app.routes)
app = Starlette(routes=routes, lifespan=lifespan,
                middleware=[Middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['GET', 'POST', 'DELETE', 'OPTIONS'], allow_headers=['*'], expose_headers=['Mcp-Session-Id'])])
