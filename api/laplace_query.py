"""Read-only query layer over the Construct Laplace SQLite release (release K1.2). Used by the HTTP API and the MCP server.

Everything returns plain dicts/lists (JSON-ready). Every relationship answer carries its provenance:
paper ids, hypothesis ids, statements and verdicts, so a caller can cite and check it.
"""
import sqlite3, re, os, collections, json

DB = os.environ.get('LAPLACE_DB') or os.environ.get('ATLAS_DB') or next((p for p in [os.path.join(os.path.dirname(__file__), 'data', 'construct_laplace.sqlite'),
    os.path.join(os.path.dirname(__file__), '..', 'release', 'construct_atlas_k12.sqlite')] if os.path.exists(p)), 'construct_laplace.sqlite')

def _norm(s):
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).split())

class Laplace:
    def __init__(self, path=DB):
        self.db = sqlite3.connect(f'file:{path}?mode=ro', uri=True, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.E = {r['entry_id']: dict(r) for r in self.db.execute("SELECT * FROM entries WHERE status='active'")}
        self.kids = collections.defaultdict(list)
        for k, e in self.E.items():
            if e['parent_id'] in self.E: self.kids[e['parent_id']].append(k)
        self._build_search()
        self._build_ranker()

    # ---------- search index (entry names, aliases, and every paper-level construct name mapped to an entry) ----------
    def _build_search(self):
        self.s = sqlite3.connect(':memory:', check_same_thread=False)
        self.s.execute("CREATE VIRTUAL TABLE t USING fts5(entry_id UNINDEXED, kind UNINDEXED, text, tokenize='porter unicode61')")
        rows, self.exact = [], collections.defaultdict(collections.Counter)
        for k, e in self.E.items():
            rows.append((k, 'name', e['name'])); self.exact[_norm(e['name'])][k] += 100
            for a in (e['aliases'] or '').split(';'):
                a = a.replace('(inverse)', '').replace('(reverse)', '').strip()
                if a: rows.append((k, 'alias', a)); self.exact[_norm(a)][k] += 50
        for r in self.db.execute("SELECT entry_id, name, authors_terms FROM constructs WHERE entry_id != '' AND row_status IS NULL"):
            if r['entry_id'] not in self.E: continue
            rows.append((r['entry_id'], 'paper_name', r['name'])); self.exact[_norm(r['name'])][r['entry_id']] += 1
        for r in self.db.execute("SELECT c.entry_id, m.variable_name FROM measures m JOIN constructs c ON c.paper_id = m.paper_id AND c.construct_id = m.construct_id WHERE c.entry_id != '' AND c.row_status IS NULL AND m.row_status IS NULL AND m.variable_name IS NOT NULL"):
            if r['entry_id'] in self.E and r['variable_name']:
                rows.append((r['entry_id'], 'measure', r['variable_name'])); self.exact[_norm(r['variable_name'])][r['entry_id']] += 1
        self.s.executemany('INSERT INTO t VALUES (?,?,?)', rows)

    def _build_ranker(self):
        import numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.np = np; self.ids = sorted(self.E)
        docs = collections.defaultdict(list)
        for r in self.db.execute("SELECT entry_id, name FROM constructs WHERE entry_id != '' AND row_status IS NULL"):
            if r[0] in self.E: docs[r[0]].append(r[1])
        T = [' . '.join([self.E[k]['name']] * 3 + [a for a in (self.E[k]['aliases'] or '').split(';') if a.strip()] * 2 + docs[k]) for k in self.ids]
        D = [self.E[k]['definition'] for k in self.ids]
        self.vw = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words='english').fit(T + D)
        self.vc = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5), sublinear_tf=True, min_df=2).fit(T)
        self.XW, self.XD, self.XC = self.vw.transform(T), self.vw.transform(D), self.vc.transform(T)
        self.pop = np.log1p(np.array([len(docs[k]) for k in self.ids]))
        self.emb = None  # optional dense vectors (entry_emb.npy, bge-small) if fastembed is installed
        try:
            here = os.path.dirname(__file__)
            eids = list(np.load(os.path.join(here, 'entry_emb_ids.npy')))
            if eids == self.ids:
                from fastembed import TextEmbedding
                self.emb = np.load(os.path.join(here, 'entry_emb.npy')); self.model = TextEmbedding('BAAI/bge-small-en-v1.5')
        except Exception:
            self.emb = None

    def resolve(self, q, limit=5):
        """Alias-aware lookup. Exact matches on names, aliases, paper-level names and measure names first; then a hybrid of
        TF-IDF (words and character n-grams over names, aliases, paper wordings, definitions) and, when available, dense embeddings.
        Silver evaluation (500 author wordings not in the index): recall@1 0.41, recall@5 0.68 with embeddings."""
        np = self.np
        if not hasattr(self, 'ids'): self._build_ranker()
        s = 0.6 * (self.XW @ self.vw.transform([q]).T).toarray().ravel() + 0.1 * (self.XD @ self.vw.transform([q]).T).toarray().ravel() + 0.3 * (self.XC @ self.vc.transform([q]).T).toarray().ravel()
        if self.emb is not None:
            v = np.array(list(self.model.embed([q])))[0]; v /= np.linalg.norm(v)
            s = 0.7 * s + 0.3 * (self.emb @ v)
        s = s + 0.02 * self.pop
        score = collections.Counter({self.ids[i]: float(s[i]) for i in np.argsort(-s)[:max(limit, 20)]})
        for k, v in self.exact.get(_norm(q), {}).items(): score[k] += 10 + 0.01 * v
        out = []
        for k, sc in score.most_common(limit):
            e = self.E[k]
            out.append({'entryId': k, 'name': e['name'], 'level': e['level'], 'parent': self.E.get(e['parent_id'], {}).get('name'),
                        'definition': e['definition'], 'score': round(sc, 2)})
        return out

    # ---------- entries ----------
    def entry(self, eid):
        e = self.E.get(eid)
        if not e: return None
        path, x = [], e['parent_id']
        while x in self.E: path.insert(0, {'entryId': x, 'name': self.E[x]['name']}); x = self.E[x]['parent_id']
        n = self.db.execute("SELECT COUNT(*) c, COUNT(DISTINCT paper_id) p FROM constructs WHERE entry_id=? AND row_status IS NULL", (eid,)).fetchone()
        sec = [dict(r) for r in self.db.execute("SELECT parent_entry, relation, papers_stating FROM secondary_parents WHERE child_entry=?", (eid,))]
        return {'entryId': eid, 'name': e['name'], 'definition': e['definition'], 'level': e['level'], 'signConvention': e['sign_convention'],
                'relation': e['relation'], 'path': path, 'children': [{'entryId': k, 'name': self.E[k]['name'], 'relation': self.E[k]['relation']} for k in self.kids[eid]],
                'secondaryParents': sec, 'aliases': [a.strip() for a in (e['aliases'] or '').split(';') if a.strip()],
                'citations': e['citations'], 'constructsMapped': n['c'], 'papers': n['p']}

    def _scope(self, eid, scope):
        if scope == 'exact': return {eid}
        out, st = set(), [eid]
        while st:
            x = st.pop(); out.add(x); st += self.kids[x]
        return out

    # ---------- relationships ----------
    def relationships(self, eid, role='both', scope='children', min_papers=1, limit=50):
        """Predictors and/or outcomes of an entry, aggregated over papers. scope: exact | children (entry plus its narrower entries)."""
        S = self._scope(eid, scope); res = {}
        q = {'predictors': ('target_entry', 'source_entry'), 'outcomes': ('source_entry', 'target_entry')}
        for side in (['predictors', 'outcomes'] if role == 'both' else [role]):
            here, other = q[side]
            agg = collections.defaultdict(lambda: {'papers': set(), 'pos': set(), 'neg': set(), 'nonlin': set(), 'supported': 0, 'n': 0})
            ph = ','.join('?' * len(S))
            for r in self.db.execute(f"SELECT * FROM evidence_links WHERE {here} IN ({ph}) AND {other} NOT IN ({ph})", list(S) * 2):
                a = agg[r[other]]; a['papers'].add(r['paper_id']); a['n'] += 1
                a['supported'] += r['verdict'] in ('supported', 'partially_supported', 'marginally_supported')
                if r['shape']: a['nonlin'].add(r['paper_id'])
                elif r['sign'] == 1: a['pos'].add(r['paper_id'])
                elif r['sign'] == -1: a['neg'].add(r['paper_id'])
            rows = [{'entryId': k, 'name': self.E[k]['name'], 'papers': len(a['papers']), 'papersPositive': len(a['pos']), 'papersNegative': len(a['neg']),
                     'papersCurvilinear': len(a['nonlin']), 'hypotheses': a['n'], 'shareSupported': round(a['supported'] / a['n'], 2)}
                    for k, a in agg.items() if k in self.E and len(a['papers']) >= min_papers]
            rows.sort(key=lambda r: (-r['papers'], r['name']))
            res[side] = rows[:limit]
        return {'entryId': eid, 'name': self.E[eid]['name'], 'scope': scope, **res}

    def evidence(self, source, target, scope='exact', limit=100):
        """Hypothesis-level evidence for source -> target with statements, verdicts and quotes."""
        S, T = self._scope(source, scope), self._scope(target, scope)
        out = []
        for r in self.db.execute(f"""SELECT l.*, h.statement, h.direction, h.verdict_quote, h.label, p.short_label, p.year, p.journal, p.title, p.doi
                FROM evidence_links l JOIN hypotheses h ON h.hypothesis_key = l.paper_id || ':' || l.hypothesis_id JOIN papers p ON p.paper_id = l.paper_id
                WHERE l.source_entry IN ({','.join('?' * len(S))}) AND l.target_entry IN ({','.join('?' * len(T))}) ORDER BY p.year, p.short_label, p.title, l.paper_id, l.hypothesis_id LIMIT ?""", list(S) + list(T) + [limit]):
            out.append({'paper': {'paperId': r['paper_id'], 'label': r['short_label'], 'year': r['year'], 'journal': r['journal'], 'title': r['title'], 'doi': r['doi']},
                        'hypothesis': r['label'], 'kind': r['kind'], 'statement': r['statement'], 'direction': r['direction'], 'adjustedSign': r['sign'],
                        'shape': r['shape'], 'verdict': r['verdict'], 'verdictQuote': r['verdict_quote'], 'mappingNeedsReview': r['mapping_needs_review']})
        conf = self.db.execute("SELECT n_papers, papers_positive_supported, papers_negative_supported FROM opposite_sign_pairs WHERE source_entry=? AND target_entry=?", (source, target)).fetchone()
        return {'source': self.E[source]['name'], 'target': self.E[target]['name'], 'scope': scope, 'n': len(out), 'oppositeSign': dict(conf) if conf else None, 'evidence': out}

    def measures(self, eid, limit=50):
        rows = [dict(r) for r in self.db.execute("SELECT * FROM entry_measures WHERE entry_id=? ORDER BY year DESC, short_label, paper_id LIMIT ?", (eid, limit))]
        scales = collections.Counter((r['scale'] or 'unspecified').split(' ')[0].lower() for r in rows)
        return {'entryId': eid, 'name': self.E[eid]['name'], 'n': len(rows), 'scaleTypes': scales.most_common(8), 'measures': rows}

    def paper(self, pid):
        p = self.db.execute("SELECT * FROM papers WHERE paper_id=?", (pid,)).fetchone()
        if not p: return None
        hs = [dict(r) for r in self.db.execute("SELECT hypothesis_id, label, kind, statement, direction, verdict FROM hypotheses WHERE paper_id=? AND counts_for_inclusion=1 AND row_status IS NULL", (pid,))]
        cs = [dict(r) for r in self.db.execute("SELECT construct_id, name, entry_id, polarity, fit FROM constructs WHERE paper_id=? AND row_status IS NULL", (pid,))]
        for c in cs: c['entryName'] = self.E.get(c['entry_id'], {}).get('name')
        t = self.db.execute("SELECT * FROM paper_topics WHERE paper_id=?", (pid,)).fetchone()
        return {**{k: p[k] for k in ('paper_id', 'doi', 'title', 'journal', 'year', 'short_label', 'abstract', 'in_scope')},
                'topics': [x for x in (t['topic1'], t['topic2'], t['topic3']) if x] if t else [], 'constructs': cs, 'hypotheses': hs}

    def search_papers(self, entry=None, topic=None, journal=None, year_from=None, year_to=None, limit=50):
        where, args = ['p.in_scope=1'], []
        if entry: where.append(f"p.paper_id IN (SELECT paper_id FROM constructs WHERE entry_id IN ({','.join('?' * len(self._scope(entry, 'children')))}))"); args += list(self._scope(entry, 'children'))
        if topic: where.append('p.paper_id IN (SELECT paper_id FROM paper_topics WHERE ? IN (topic1, topic2, topic3))'); args.append(topic)
        if journal: where.append('p.journal = ?'); args.append(journal)
        if year_from: where.append('p.year >= ?'); args.append(year_from)
        if year_to: where.append('p.year <= ?'); args.append(year_to)
        rows = self.db.execute(f"SELECT p.paper_id, p.short_label, p.year, p.journal, p.title FROM papers p WHERE {' AND '.join(where)} ORDER BY p.year DESC, p.short_label, p.title, p.paper_id LIMIT ?", args + [limit])
        return [dict(r) for r in rows]

    def topics(self):
        return [dict(r) | {'papers': self.db.execute("SELECT COUNT(*) FROM paper_topics pt JOIN papers p USING(paper_id) WHERE p.in_scope=1 AND ? IN (topic1, topic2, topic3)", (r['topic_id'],)).fetchone()[0]}
                for r in self.db.execute('SELECT * FROM topics')]

    # ---------- authors ----------
    def search_authors(self, q, limit=20):
        t = f"%{_norm(q)}%" if False else f"%{q.strip().lower()}%"
        rows = self.db.execute("""SELECT a.person_id, a.display_name, COUNT(DISTINCT CASE WHEN p.in_scope=1 THEN pa.paper_id END) n_papers, a.first_year, a.last_year
            FROM authors a JOIN paper_authors pa USING(person_id) JOIN papers p USING(paper_id)
            WHERE lower(a.display_name) LIKE ? OR a.person_id IN (SELECT person_id FROM paper_authors WHERE lower(printed_name) LIKE ?)
            GROUP BY a.person_id ORDER BY n_papers DESC LIMIT ?""", (t, t, limit))
        return [dict(r) for r in rows]

    def author(self, person_id, min_papers=1):
        a = self.db.execute("SELECT * FROM authors WHERE person_id=?", (person_id,)).fetchone()
        if not a: return None
        papers = [dict(r) for r in self.db.execute("""SELECT p.paper_id, p.short_label, p.year, p.journal, p.title, pa.position FROM paper_authors pa JOIN papers p USING(paper_id)
            WHERE pa.person_id=? AND p.in_scope=1 ORDER BY p.year, p.short_label, p.title, p.paper_id""", (person_id,))]
        pids = [p['paper_id'] for p in papers]; ph = ','.join('?' * len(pids)) or "''"
        journals = collections.Counter(p['journal'] for p in papers)
        topics = collections.Counter(t for r in self.db.execute(f"SELECT topic1, topic2, topic3 FROM paper_topics WHERE paper_id IN ({ph})", pids) for t in r if t)
        TN = dict(self.db.execute("SELECT topic_id, name FROM topics").fetchall())
        CL = {r['class_id']: dict(r) for r in self.db.execute("SELECT * FROM classes")}
        ent = collections.defaultdict(set)
        for pid, eid in self.db.execute(f"SELECT paper_id, entry_id FROM constructs WHERE paper_id IN ({ph}) AND entry_id IS NOT NULL AND entry_id!='' AND row_status IS NULL", pids):
            if eid in self.E: ent[eid].add(pid)
        cls, circ = collections.defaultdict(set), collections.defaultdict(set)
        for eid, ps in ent.items():
            c = CL.get(self.E[eid]['class_id']) or {}
            cls[c.get('name')] |= ps; circ[c.get('circle')] |= ps
        links = collections.defaultdict(lambda: {'papers': set(), 'signs': collections.Counter()})
        for r in self.db.execute(f"SELECT paper_id, source_entry, target_entry, sign FROM evidence_links WHERE paper_id IN ({ph}) AND kind='direct'", pids):
            if r['source_entry'] in self.E and r['target_entry'] in self.E and r['source_entry'] != r['target_entry']:
                l = links[(r['source_entry'], r['target_entry'])]; l['papers'].add(r['paper_id']); l['signs'][r['sign']] += 1
        co = collections.Counter()
        for r in self.db.execute(f"SELECT person_id FROM paper_authors WHERE paper_id IN ({ph}) AND person_id!=?", pids + [person_id]): co[r[0]] += 1
        names = dict(self.db.execute(f"SELECT person_id, display_name FROM authors WHERE person_id IN ({','.join('?' * len(co)) or chr(39)*2})", list(co)).fetchall())
        return {'person': {k: a[k] for k in ('person_id', 'display_name', 'first_year', 'last_year')}, 'nPapers': len(papers), 'journals': journals.most_common(), 'topics': [(TN.get(t, t), n) for t, n in topics.most_common()],
                'classes': sorted(((k, len(v)) for k, v in cls.items()), key=lambda x: -x[1]),
                'constructs': sorted(({'entryId': e, 'name': self.E[e]['name'], 'papers': len(ps)} for e, ps in ent.items()), key=lambda x: -x['papers'])[:40],
                'relationships': sorted(({'source': s, 'sourceName': self.E[s]['name'], 'target': t, 'targetName': self.E[t]['name'], 'papers': len(l['papers']),
                                          'signs': dict(l['signs'])} for (s, t), l in links.items() if len(l['papers']) >= min_papers), key=lambda x: -x['papers']),
                'coauthors': [{'personId': p, 'name': names.get(p), 'sharedPapers': n} for p, n in co.most_common(30)], 'papers': papers}


# ---------- v5 additions (2026-09-30): full-text search over papers, facets, filters, measures by approach ----------
DESIGN = ['panel', 'cross-sectional', 'experiment', 'qualitative case', 'event study', 'time series', 'other']
_J = lambda s: json.loads(s) if s else []


def _v5_init(self):
    db = self.db
    have = {r[0] for r in db.execute("SELECT name FROM sqlite_master")}
    self.has_mt = 'measure_tags' in have
    self.MA = {r['code']: dict(r) for r in db.execute('SELECT * FROM measurement_approaches')} if 'measurement_approaches' in have else {}
    P = {r['paper_id']: dict(r) for r in db.execute('SELECT paper_id, title, authors, abstract, journal, year, short_label, doi, theories FROM papers WHERE in_scope=1')}
    self.P = P
    fac = {p: {'design': set(), 'method': set(), 'theory': set(_J(r['theories'])), 'measurement': set(), 'data_type': set(), 'topic': set()} for p, r in P.items()}
    for r in db.execute('SELECT paper_id, data_structure, methods_estimation FROM studies'):
        if r[0] in fac:
            fac[r[0]]['design'].update(x for x in _J(r[1]) if x); fac[r[0]]['method'].update(x for x in _J(r[2]) if x and x not in ('Other', 'iv'))
    for r in db.execute('SELECT paper_id, type FROM data_sources'):
        if r[0] in fac and r[1] and r[1] != 'other': fac[r[0]]['data_type'].add(r[1])
    for r in db.execute('SELECT paper_id, topic1, topic2, topic3 FROM paper_topics'):
        if r[0] in fac: fac[r[0]]['topic'].update(t for t in r[1:] if t)
    if self.has_mt:
        for r in db.execute('SELECT paper_id, codes FROM measure_tags'):
            if r[0] in fac and r[1]: fac[r[0]]['measurement'].update(c for c in r[1].split(';') if c)
    self.fac = fac
    # full-text index over papers
    cons, hyp, meas = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
    for r in db.execute('SELECT paper_id, name, entry_id, authors_terms FROM constructs WHERE row_status IS NULL'):
        if r[0] in P: cons[r[0]] += [r[1] or '', self.E.get(r[2], {}).get('name', ''), r[3] or '']
    for r in db.execute('SELECT paper_id, statement FROM hypotheses WHERE row_status IS NULL'):
        if r[0] in P: hyp[r[0]].append(r[1] or '')
    for r in db.execute('SELECT paper_id, variable_name, description FROM measures WHERE row_status IS NULL'):
        if r[0] in P: meas[r[0]].append(f"{r[1] or ''}: {r[2] or ''}")
    s = self.s
    s.execute("CREATE VIRTUAL TABLE pf USING fts5(paper_id UNINDEXED, title, authors, abstract, constructs, hypotheses, measures, labels, tokenize='porter unicode61')")
    rows = []
    for p, r in P.items():
        f = fac[p]
        labels = ' '.join(list(f['theory']) + list(f['method']) + list(f['design']) + [self.MA.get(c, {}).get('label', c) for c in f['measurement']])
        rows.append((p, r['title'] or '', ' '.join(_J(r['authors'])) if (r['authors'] or '').startswith('[') else (r['authors'] or ''), r['abstract'] or '',
                     ' '.join(cons[p]), ' '.join(hyp[p]), ' '.join(meas[p]), labels))
    s.executemany('INSERT INTO pf VALUES (?,?,?,?,?,?,?,?)', rows)


def _fts_query(q):
    toks = re.findall(r'[A-Za-z0-9]+', q or '')
    if not toks: return None
    return ' AND '.join(f'"{t}"' + ('*' if len(t) > 3 else '') for t in toks)


def _match(self, p, journal=None, year_from=None, year_to=None, topic=None, design=None, theory=None, method=None, measurement=None, data_type=None, entry=None):
    r = self.P.get(p); f = self.fac.get(p)
    if not r: return False
    if journal and r['journal'] != journal and self._jshort.get(r['journal']) != journal: return False
    if year_from and (r['year'] or 0) < int(year_from): return False
    if year_to and (r['year'] or 9999) > int(year_to): return False
    for k, v in (('topic', topic), ('design', design), ('theory', theory), ('method', method), ('measurement', measurement), ('data_type', data_type)):
        if v:
            want = {x.strip() for x in str(v).split(',') if x.strip()}
            if not (f[k] & want) and not any(w.lower() == x.lower() for w in want for x in f[k]): return False
    if entry and p not in self._entry_papers(entry): return False
    return True


def _entry_papers(self, entry):
    S = self._scope(entry, 'children') if entry in self.E else set()
    if not S: return set()
    ph = ','.join('?' * len(S))
    return {r[0] for r in self.db.execute(f'SELECT DISTINCT paper_id FROM constructs WHERE entry_id IN ({ph})', list(S))}


def _pcard(self, p, extra=None):
    r = self.P[p]
    return {'paperId': p, 'label': r['short_label'], 'year': r['year'], 'journal': r['journal'], 'title': r['title'], 'doi': r['doi'], **(extra or {})}


FIELDS = ['title', 'authors', 'abstract', 'constructs', 'hypotheses', 'measures', 'labels']


def search(self, q, limit=20, **filters):
    """Search papers (title, authors, abstract, constructs, hypotheses, measures, theory/method/design/measurement labels) and dictionary entries.
    Every word must appear in the paper (prefix match for words longer than 3 letters). Ranked by BM25 with weights favouring title, authors and constructs."""
    fq = _fts_query(q); papers = []
    if fq:
        toks = re.findall(r'[A-Za-z0-9]+', q)
        rows, seen = [], set()
        # the exact phrase first (for multi-word queries), then papers that contain every word anywhere
        for query in ([' "' + ' '.join(toks) + '"'] if len(toks) > 1 else []) + [fq]:
            for p, sc in self.s.execute("SELECT paper_id, bm25(pf, 0, 8, 9, 4, 6, 3, 2, 4) AS sc FROM pf WHERE pf MATCH ? ORDER BY sc LIMIT 3000", (query,)).fetchall():
                if p not in seen: seen.add(p); rows.append((p, sc))
        for p, sc in rows:
            if not self._match(p, **filters): continue
            where = [c for c in FIELDS if self.s.execute("SELECT 1 FROM pf WHERE paper_id=? AND pf MATCH ?", (p, '{' + c + '} : (' + ' OR '.join(f'"{t}"' for t in toks) + ')')).fetchone()] if len(papers) < limit else []
            papers.append((p, sc, where))
    n = len(papers)
    return {'query': q, 'filters': {k: v for k, v in filters.items() if v}, 'papersFound': n,
            'papers': [self._pcard(p, {'matchedIn': w, 'score': round(-sc, 2)}) for p, sc, w in papers[:limit]],
            'constructs': self.resolve(q, 5) if q else []}


def find_papers(self, q=None, limit=50, offset=0, **filters):
    """Filtered paper list, newest first (or by relevance when q is given)."""
    if q: ids = [x['paperId'] for x in self.search(q, limit=100000, **filters)['papers']]
    else: ids = sorted((p for p in self.P if self._match(p, **filters)), key=lambda p: (-(self.P[p]['year'] or 0), self.P[p]['short_label'] or '', self.P[p]['title'] or '', p))
    return {'total': len(ids), 'offset': offset, 'papers': [self._pcard(p) for p in ids[offset:offset + limit]]}


def facets(self, **filters):
    """Values of every filter with the number of in-scope papers for each (under the given filters)."""
    ids = [p for p in self.P if self._match(p, **filters)]
    out = {'papers': len(ids), 'journal': collections.Counter(self.P[p]['journal'] for p in ids).most_common(),
           'year': [min((self.P[p]['year'] for p in ids), default=None), max((self.P[p]['year'] for p in ids), default=None)]}
    TN = dict(self.db.execute('SELECT topic_id, name FROM topics').fetchall())
    for k in ('topic', 'design', 'theory', 'method', 'measurement', 'data_type'):
        c = collections.Counter(x for p in ids for x in self.fac[p][k])
        lim = 80 if k == 'theory' else 60
        out[k] = [{'value': v, 'label': TN.get(v) if k == 'topic' else self.MA.get(v, {}).get('label') if k == 'measurement' else v, 'papers': n} for v, n in c.most_common(lim)]
    return out


def measurement_approaches(self):
    """The measurement-approach codes, what each covers, and how many measures and papers carry it."""
    if not self.has_mt: return []
    cm, cp = collections.Counter(), collections.defaultdict(set)
    for p, codes in self.db.execute('SELECT paper_id, codes FROM measure_tags'):
        for c in (codes or '').split(';'):
            if c: cm[c] += 1; cp[c].add(p)
    return [{**v, 'measures': cm[k], 'papers': len(cp[k] & set(self.P))} for k, v in self.MA.items()]


def find_measures(self, q=None, approach=None, entry=None, limit=50, offset=0, **filters):
    """Measures across papers: filter by measurement approach codes (e.g. TXT_ML,TXT_DICT), by a dictionary entry (with narrower entries),
    by words in the measure name or description, and by paper filters. Returns the measure, how it was built, the construct it measures and the paper."""
    where, args = ['1=1'], []
    if approach and not self.has_mt: return {'total': 0, 'papers': 0, 'offset': offset, 'measures': [], 'note': 'this release has no measurement-approach tags'}
    if approach and self.has_mt:
        cs = [c.strip().upper() for c in approach.split(',') if c.strip()]
        where.append('(' + ' OR '.join("(';' || t.codes || ';') LIKE ?" for _ in cs) + ')'); args += [f'%;{c};%' for c in cs]
    if entry:
        S = self._scope(entry, 'children'); where.append(f"c.entry_id IN ({','.join('?' * len(S))})"); args += list(S)
    for w in re.findall(r'[A-Za-z0-9]+', q or ''):
        where.append('(lower(m.variable_name) LIKE ? OR lower(m.description) LIKE ?)'); args += [f'%{w.lower()}%'] * 2
    join_t = 'LEFT JOIN measure_tags t ON t.measure_key = m.measure_key' if self.has_mt else ''
    rows = self.db.execute(f"""SELECT m.measure_key, m.paper_id, m.variable_name, m.description, m.scale, m.level, m.time_window, c.name AS construct, c.entry_id,
        {'t.codes' if self.has_mt else "''"} AS codes FROM measures m LEFT JOIN constructs c ON c.paper_id = m.paper_id AND c.construct_id = m.construct_id {join_t}
        WHERE {' AND '.join(where)} ORDER BY m.paper_id""", args).fetchall()
    rows = [r for r in rows if r['paper_id'] in self.P and self._match(r['paper_id'], **filters)]
    rows.sort(key=lambda r: (-(self.P[r['paper_id']]['year'] or 0), self.P[r['paper_id']]['short_label'] or '', self.P[r['paper_id']]['title'] or '', r['paper_id']))
    out = []
    for r in rows[offset:offset + limit]:
        out.append({'paper': self._pcard(r['paper_id']), 'measure': r['variable_name'], 'description': r['description'], 'scale': r['scale'], 'level': r['level'],
                    'timeWindow': r['time_window'], 'construct': r['construct'], 'entryId': r['entry_id'] or None, 'entryName': self.E.get(r['entry_id'], {}).get('name'),
                    'approach': [{'code': c, 'label': self.MA.get(c, {}).get('label', c)} for c in (r['codes'] or '').split(';') if c]})
    return {'total': len(rows), 'papers': len({r['paper_id'] for r in rows}), 'offset': offset, 'measures': out}


def paper_full(self, pid):
    """Everything about one paper: metadata, authors, topics, design, methods, theories, data sources, constructs, hypotheses, measures."""
    base = self.paper(pid)
    if not base: return None
    au = [dict(r) for r in self.db.execute('SELECT position, printed_name, person_id FROM paper_authors WHERE paper_id=? ORDER BY position', (pid,))]
    st = [{'study': r['study_id'], 'sample': r['sample'], 'setting': r['setting'], 'period': r['period'], 'countries': _J(r['countries']), 'industries': _J(r['industries']),
           'design': _J(r['data_structure']), 'methods': _J(r['methods_estimation'])} for r in self.db.execute('SELECT * FROM studies WHERE paper_id=? AND row_status IS NULL', (pid,))]
    ds = [{'name': r['name_raw'], 'databases': _J(r['canonical_names']), 'type': r['type']} for r in self.db.execute('SELECT * FROM data_sources WHERE paper_id=? AND row_status IS NULL', (pid,))]
    ms = self.find_measures(limit=500, **{})['measures'] if False else [
        {'measure': r['variable_name'], 'construct': r['construct_id'], 'description': r['description'], 'scale': r['scale'], 'level': r['level'],
         'approach': [c for c in (r['codes'] or '').split(';') if c]}
        for r in self.db.execute(f"SELECT m.*, {'t.codes' if self.has_mt else chr(39)*2} AS codes FROM measures m {'LEFT JOIN measure_tags t ON t.measure_key=m.measure_key' if self.has_mt else ''} WHERE m.paper_id=? AND m.row_status IS NULL", (pid,))]
    f = self.fac.get(pid, {})
    return {**base, 'authors': au, 'theories': sorted(f.get('theory', ())), 'studies': st, 'dataSources': ds, 'measures': ms}


def _init_v5_hook(orig):
    def __init__(self, path=DB):
        orig(self, path)
        self._jshort = {'Strategic Management Journal': 'SMJ', 'Academy of Management Journal': 'AMJ', 'Administrative Science Quarterly': 'ASQ',
                        'Management Science': 'MS', 'Organization Science': 'OS', 'Strategy Science': 'SS'}
        _v5_init(self)
    return __init__


Laplace.__init__ = _init_v5_hook(Laplace.__init__)
for _f in (_match, _entry_papers, _pcard, search, find_papers, facets, measurement_approaches, find_measures, paper_full):
    setattr(Laplace, _f.__name__, _f)


Atlas = Laplace   # old name, kept for scripts written before 2026-09-30
