# Phase 2: Trusted Assistant

## Goal
Improve trust, legal context, and workflow value without sacrificing source discipline.

## Product Additions
- Tracked-law subscriptions and change alerts
- Change summaries between versions
- Legislative history from Riigikogu
- Selected case law as interpretive support
- Internal legal reviewer dashboard
- Citizen legal self-service workflows for common question types

## Retrieval Enhancements
- Better query classification
- Domain-specific reranking features
- Citation graph traversal for related provisions
- Query rewriting for abbreviations and common legal aliases

## Data Additions
- `bill`
- `court_decision`
- `act_case_link`
- `diff_record`
- subscription and alert tables

## Review And Governance
- Reviewer queue for low-confidence answers
- Structured review labels for factuality and citation quality
- Replay tooling for failed or disputed queries
- Change monitoring for source-ingest failures and stale indexes

## Fine-Tuning Scope
Only fine-tune after retrieval quality is stable.

Focus fine-tuning on:
- citation formatting
- refusal behavior
- answer structure
- change-summary generation
- accountant workflow language

Do not fine-tune to store statutory knowledge in model weights.

## UX Additions
- Dashboard for tracked acts and recent changes
- Matter folders for saved research
- Memo export with citations
- Filters for current, historical, and future-effective wording
- Guided intake flows for common citizen questions

## Citizen Workflow Expansion
Add guided question flows for:
- buying a house or apartment
- fines and challenge rights
- employment termination and salary disputes
- common consumer and administrative issues

For each workflow, the assistant should:
- classify the legal domain
- ask only the minimum missing facts
- identify deadlines and procedural rights
- separate general law from case-specific uncertainty
- cite the exact legal basis for each practical step

## Operational Requirements
- Audit logs for answer generation
- Alerting on ingestion failures
- Index freshness monitoring
- Dataset versioning for evaluation runs

## Exit Criteria
- Users can track laws and receive meaningful change alerts
- Reviewers can inspect and score answers
- Legislative history and selected case law improve answer quality
- Refusal and uncertainty handling are reliable
- Common citizen workflows are supported with clarification-first logic
