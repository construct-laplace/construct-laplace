# Data guide

One SQLite file, `data/construct_laplace.sqlite` (run `python3 setup.py` to unpack it). The CSV files in `data/csv/` are copies of the main tables, limited to the papers in scope.

Ids: papers `p123`, dictionary entries `c01.e001`, constructs and hypotheses are numbered within their paper (`paper_id:construct_id`, `paper_id:hypothesis_id`). An empty `row_status` marks a valid row; `not_setoff` marks a statement that does not count as a formal hypothesis, and `wrong_text` a row that came from another article's text. Such rows are kept in the file and left out of every count, page and query.

## Papers and scope

**papers.** One row per article that reached extraction, in scope or not.
`paper_id`, `doi`, `title`, `title_flags` (how the title was cleaned), `journal`, `year` (year of the volume and issue), `authors` (JSON list), `short_label` (as cited), `abstract`, `abstract_source` (web_of_science, crossref, openalex, paper_first_page, none), `in_scope` (1 or 0), `scope_code` and `scope_category` (the code of the article ledger: IN, or the first exclusion rule the paper fails), `streams`, `theories` (JSON lists).

**data/article_ledger.csv.** Every journal article of the six journals (28,193), including those screened out before extraction, with its status and exclusion code. **data/exclusion_codes.csv** explains the codes (R1 to R4 record rules, H1 to H4 hypothesis rules, T1 to T4 topic rules).

## Hypotheses, constructs and measures (one paper at a time)

**hypotheses.** The formal hypotheses each paper states and tests.
`label` (as printed, e.g. Hypothesis 2a), `statement` (as written in the paper), `kind` (direct, moderation, mediation, effect_strength), `source_construct`, `target_construct`, `moderator_construct`, `mediator_constructs` (construct ids of the paper), `direction` (positive, negative, inverted_u, u_shaped, conditional, not_stated), `moderator_effect` (strengthens, weakens, reverses, conditions), `verdict` (the authors' own conclusion: supported, partially_supported, marginally_supported, mixed, not_supported, not_tested), `verdict_quote` (short quote from the paper), `counts_for_inclusion` (1 when the statement is set off as a hypothesis and tested).

**constructs.** Constructs as each paper names and defines them, and the dictionary entry each is filed under.
`name`, `authors_terms` (the authors' own terms), `definition` (from the paper), `definition_type` (conceptual, operational, both, missing), `entry_id`, `polarity` (1, or -1 when the construct is the opposite pole of the entry, e.g. "firm smallness" under Firm size), `fit` (exact, variant, measure, broader, none), `confidence`, `mapping_source` (two_readers_agree, adjudicated, reviewed, new_entry, unmapped), `needs_review` (1 when the filing was not confirmed).

**measures.** How each construct was measured: `construct_id`, `study_id`, `variable_name`, `description`, `scale`, `level`, `time_window`, `reverse_coded`, `data_source_ids`.
**measure_tags** and **measurement_approaches.** The measurement approach of each measure (archival, survey, text analysis by machine learning, and so on; 12 codes).

**studies.** Sample, setting, period, countries, industries, data structure and methods of each empirical study in a paper.
**data_sources.** Data sources named in each paper: the name as written, canonical database names, type and category. **data_source_additions** lists canonical names added by fixed patterns.

## The construct dictionary

**entries.** Field-level constructs that paper constructs are filed under.
`entry_id`, `class_id`, `name`, `definition`, `level`, `sign_convention` (what higher values mean), `parent_id` and `relation` (type_of, aspect_of, or group_only when the parent is only a heading and evidence does not roll up), `basis` (literature, author, expert), `citations`, `citation_check`, `aliases`, `status` (active, merged, unused), `merged_into`.
**classes.** The 22 construct classes and 7 broader circles. **secondary_parents.** Second parents an entry also belongs to. **tree_edge_support.** Papers whose authors state the type_of or aspect_of relation.

## Relations across papers

**evidence_links.** One row per hypothesis that links two dictionary entries: `source_entry`, `target_entry`, `sign` (adjusted for polarity), `shape`, `verdict`, `kind`.
**moderator_links.** Moderation hypotheses at entry level: `moderator_entry`, `source_entry`, `target_entry`, `effect`, `verdict`.
**entry_edges.** Evidence per ordered pair of entries, counted in distinct papers: `n_papers`, `n_hypotheses`, `papers_positive`, `papers_negative`, `papers_nonlinear`, `papers_unsigned`, `support_share` (supported 1, partial, marginal or mixed 0.5, not supported 0).
**opposite_sign_pairs.** Pairs of entries with supported findings in both directions, usually from different settings or conditions: `n_papers`, `papers_positive_supported`, `papers_negative_supported`.

## Topics and authors

**topics** and **paper_topics.** 19 research topics and up to three per paper.
**authors** and **paper_authors.** Disambiguated authors of the papers (names and papers only; no institutions).
