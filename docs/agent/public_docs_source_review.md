# Public Docs Source Review

Date: 2026-04-20

Scope:

- `README.md`
- `docs/README.md`
- `docs/ARCHITECTURE_AND_METHODS.md`
- `docs/README_USAGE_AND_OPERATIONS.md`
- `docs/CLI_REFERENCE.md`
- `docs/MCP_TOOLS.md`
- `docs/RUNTIME_TUNING.md`
- `docs/API_COMPATIBILITY.md`

## Editorial And Privacy Review

- Replaced person-like synthetic examples in the public methods and CLI docs
  with role-based examples such as `researcher@example.test`,
  `reviewer@example.test`, `role@example.test`, and
  `comparator@example.test`.
- Kept all public examples on reserved documentation domains. No real person,
  real institution, private path, or relationship-specific scenario is
  intentionally present in the public docs reviewed here.
- Preserved workflow terminology such as `relationship_paths` where it names a
  public tool surface; this is functional API vocabulary, not a private
  relationship reference.
- Tightened `.olm` export wording to state the Microsoft-documented Legacy
  Outlook for Mac boundary instead of implying universal Outlook support.

## Source-Bound Claims

| Claim area | Source standard applied | Documentation implication |
| --- | --- | --- |
| BM25 fallback | Robertson and Zaragoza, probabilistic relevance framework | BM25 is described as a ranking function with term-frequency saturation and document-length normalization, not as semantic proof. |
| ColBERT reranking | Khattab and Zaharia, ColBERT late interaction | MaxSim is described as token-vector reranking over candidates, not as calibrated factual confidence. |
| BGE-M3 dense/sparse/multi-vector behavior | BGE-M3 paper and official BGE docs | Dense, learned sparse, multi-vector, and hybrid scoring formulas are tied to upstream model documentation. |
| ChromaDB storage/query behavior | Official Chroma add/query docs | ChromaDB is described as embedding storage plus nearest-neighbor query, with metadata/document filters where supported. |
| MCP tool behavior | Official MCP tools specification | MCP is described as model-controlled tool discovery/invocation with an explicit human-in-the-loop boundary for trust and safety. |
| Outlook `.olm` export | Microsoft Support | Public setup now identifies `.olm` export as a Legacy Outlook for Mac feature. |
| spaCy NER | Official spaCy usage docs | NER is described as statistical and model-dependent; regex fallback remains explicit. |

## Methodological Limits Preserved

- Retrieval scores are ranking signals, not probabilities of truth.
- Hybrid agreement between dense, sparse, and reranking signals increases
  review priority but does not prove the underlying claim.
- QA metrics are reliable only against the labeled synthetic fixture set used
  for regression testing.
- Quote verification and provenance are stronger evidence controls than model
  similarity alone.
- Human review remains required before external sharing or counsel-facing use.

## Sources Consulted

- Robertson, S. E., and Zaragoza, H. "The Probabilistic Relevance Framework:
  BM25 and Beyond." Foundations and Trends in Information Retrieval, 2009.
  <https://www.nowpublishers.com/article/Details/INR-019>
- Khattab, O., and Zaharia, M. "ColBERT: Efficient and Effective Passage Search
  via Contextualized Late Interaction over BERT." SIGIR 2020 / arXiv:2004.12832.
  <https://arxiv.org/abs/2004.12832>
- Chen, J., Xiao, S., Zhang, P., Luo, K., Lian, D., and Liu, Z.
  "M3-Embedding: Multi-Linguality, Multi-Functionality, Multi-Granularity Text
  Embeddings Through Self-Knowledge Distillation." arXiv:2402.03216.
  <https://arxiv.org/abs/2402.03216>
- BAAI. "BGE-M3." Official BGE documentation.
  <https://bge-model.com/bge/bge_m3.html>
- Chroma. "Adding Data to Chroma Collections" and "Query and Get."
  <https://docs.trychroma.com/docs/collections/add-data> and
  <https://docs.trychroma.com/docs/querying-collections/query-and-get>
- Model Context Protocol. "Tools." Official MCP specification.
  <https://modelcontextprotocol.io/specification/draft/server/tools>
- Microsoft Support. "Export items to an archive file in Outlook for Mac."
  <https://support.microsoft.com/en-us/office/export-items-to-an-archive-file-in-outlook-for-mac-281a62bf-cc42-46b1-9ad5-6bda80ca3106>
- spaCy. "Linguistic Features: Named Entity Recognition." Official usage
  documentation. <https://spacy.io/usage/linguistic-features>
