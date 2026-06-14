# Phase 1: MVP

## Goal
Ship a narrow, trusted legal assistant for accountants that can search Estonian laws, answer questions from official sources, and cite the correct law version.

This phase stays narrow on purpose. Citizen legal workflows are prepared in the architecture but are not the primary launch scope.

## User Outcomes
- Search for applicable law by keyword or natural language
- Ask a question and receive a source-cited answer
- Inspect exact cited provisions
- Select an `as of` date to retrieve historical wording
- Compare two versions of the same act
- Receive a clarification question when the original prompt lacks facts needed for a reliable legal answer

## Required Components

### Ingestion
- Fetch selected Riigi Teataja acts in tax, employment, and company law
- Store raw source files and metadata
- Parse act hierarchy into structured provisions
- Record version boundaries and publication events

### Storage
- Postgres tables for:
  - `act`
  - `act_version`
  - `provision`
  - `citation_ref`
  - `publication_event`
  - `embedding_chunk`
  - `query_log`
  - `review_label`

### Search
- BM25 search over provision text and act titles
- Metadata filters for:
  - domain
  - act type
  - language
  - effective date
- Exact citation lookup for queries containing section references

### Retrieval
- Provision-level chunking
- Context chunk expansion to neighboring provisions
- Dense embeddings over authoritative Estonian text
- Hybrid candidate retrieval
- Reranking with official-source and date-validity preference
- Query classification for issue type and fact sensitivity

### Answering
- Grounded prompt that only uses retrieved materials
- Exact citation attachment per claim
- Explicit display of current vs historical law
- Warning when English translation is shown
- Clarification-first flow when facts are missing

## MVP Question Types
- Tax and reporting obligations for accountants
- Employment and payroll compliance questions
- Company-law obligations for businesses
- Narrow procedural questions where the system can safely ask clarifying questions before answering

### Frontend
- Search/chat page
- Source panel with clickable citations
- As-of-date selector
- Act viewer for source inspection
- Version compare page

## MVP APIs
- `POST /search`
- `POST /answer`
- `POST /compare`
- `GET /acts/:eli`
- `GET /acts/:eli/versions`
- `GET /acts/:eli/as-of?date=YYYY-MM-DD`

## Quality Gates
- Section-level citation precision is high enough for legal review
- Historical-date queries return correct versioned text
- Unsupported claims are blocked from the final answer
- Every answer is logged with retrieved source references
- Missing-fact questions trigger clarification rather than overconfident answers

## Pilot Plan
- Pilot with 5 to 10 accountant users
- Focus scenarios:
  - VAT questions
  - payroll and employment obligations
  - company reporting obligations
- Review user queries weekly and add evaluation labels

## Exit Criteria
- Usable source-cited search and Q&A
- Working historical retrieval
- Basic version compare
- Stable pilot feedback loop
