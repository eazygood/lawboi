# Phase 0: Foundation

## Goal
Establish the authoritative legal data pipeline and the core system design for an Estonian law assistant focused first on accountants.

## Product Scope
- Primary users: accountants
- Initial legal domains: tax, employment, company law
- Future expansion users: citizens with common legal self-service questions
- Authority model: Estonian official texts are authoritative; English translations are assistive only
- Product rule: no uncited answer generation

## Deliverables
- Official-source ingestion design for Riigi Teataja
- Version-aware legal data model
- Provision parser and normalizer
- Search and retrieval architecture decisions
- Evaluation framework and trust rules
- Clarification-first interaction design for fact-sensitive legal questions

## Source Strategy
- Use Riigi Teataja as the system of record for legislation
- Track act versions, effective dates, and publication references
- Keep raw source snapshots for every ingested document
- Add Riigikogu parliamentary data after the legislation pipeline is stable

## Core Architecture
- `source-ingest`: fetches raw legal source files and metadata
- `parser-normalizer`: converts source files into structured legal nodes
- `legal-kb`: stores acts, versions, provisions, and citation links
- `search-indexer`: builds sparse and vector indexes
- `retrieval-api`: runs hybrid retrieval and date filtering
- `answer-api`: produces grounded answers with citations
- `change-tracker`: computes act diffs and update events
- `admin-eval`: supports QA, replay, and legal review

## Data Model Decisions
- Store acts separately from act versions
- Store provisions as hierarchical nodes
- Attach every provision to an act version
- Persist `effective_from` and `effective_to` for each version
- Resolve and store inter-act citations as structured links
- Preserve raw hashes and source URLs for auditability

## Retrieval Decisions
- Use hybrid retrieval: BM25 plus embeddings plus metadata filters
- Apply hard date filtering before answer generation
- Prefer exact section matches when present
- Use reranking to boost official and directly relevant provisions
- Add query classification before retrieval to detect domain, procedure, and fact sensitivity
- Route fact-sensitive questions into a clarification step before final answer generation

## Clarification Strategy
- Detect when a question cannot be answered reliably from the initial prompt alone
- Ask short follow-up questions for missing legal facts
- Typical clarification cases:
  - house purchase tax obligations
  - fines and challenge rights
  - deadlines and appeal procedures
  - employment disputes and termination grounds
- Distinguish:
  - general legal information
  - case-specific procedural guidance

## Trust Rules
- No answer without supporting retrieved sources
- No mixing current and historical wording
- No silent reliance on unofficial English translations
- Every answer must include exact provision citations
- Low-evidence queries must produce a warning or refusal

## Initial Evaluation Set
- Exact section lookup
- Current-law applicability questions
- Historical-law questions
- Amendment and change-summary questions
- Ambiguous questions requiring clarification or refusal
- Citizen-style procedural questions requiring follow-up facts

## Exit Criteria
- Clear system architecture
- Stable schema for acts, versions, and provisions
- Defined trust and refusal policy
- Retrieval strategy chosen and documented
- MVP scope frozen for implementation
