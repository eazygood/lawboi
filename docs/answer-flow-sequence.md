# `/answer` Request Sequence

Sequence diagram for `POST /answer` (`src/lawboi/api/routes/answer.py`), showing the
`asyncio.gather` concurrency points: history lookup + retrieval + input moderation run
together, and — inside retrieval — `DenseSearch`/`SparseSearch`/`ProceduralAugment` run
together too (`ParallelSearch`, merged via RRF). Output moderation is necessarily
sequential since it needs the generated answer.

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant API as FastAPI /answer
    participant DB as PostgresStore (async)
    participant Retr as RetrievalService
    participant Mod as ModerationService
    participant Ans as AnswerService
    participant LLM as LLM Provider

    Client->>API: POST /answer {query, conversation_id?, as_of_date?}

    opt conversation_id is null
        API->>DB: create_conversation()
        DB-->>API: conversation_id
    end

    par asyncio.gather
        API->>DB: recent_messages(conversation_id, limit=10)
        DB-->>API: history
    and
        API->>Retr: retrieve(query, as_of_date)
        Retr->>DB: CitationShortCircuit (exact § lookup)
        DB-->>Retr: hit?
        opt no exact match
            par ParallelSearch (asyncio.gather x3)
                Retr->>DB: DenseSearch (pgvector + e5)
            and
                Retr->>DB: SparseSearch (Postgres FTS)
            and
                Retr->>DB: ProceduralAugment (2nd vector query)
            end
            DB-->>Retr: hits x3
            Retr->>Retr: merge via RRF
            Retr->>LLM: StepBackExpand: query expansion (timeout-bounded)
            LLM-->>Retr: expanded query (or unchanged on timeout)
            Retr->>DB: expanded search
            DB-->>Retr: hits
            Retr->>Retr: Rerank (Cohere, no-op without key)
        end
        Retr-->>API: provisions
    and
        API->>Mod: check(query)
        Mod->>LLM: complete_structured(prompt, ModerationResult)
        LLM-->>Mod: flagged, reason
        Mod-->>API: input_check
    end

    alt input_check.flagged
        API-->>Client: 400 ContentBlockedError
    else provisions is empty
        API->>Ans: answer(query, provisions, history)
        Ans-->>API: raises NoSourcesFoundError
        API-->>Client: 422
    else
        API->>Ans: answer(query, provisions, history)
        Ans->>LLM: complete_structured(prompt, AnswerPayload)
        LLM-->>Ans: answer, citations
        Ans->>Ans: validate_citations(citations, provisions)
        Ans-->>API: answer, citations, model_used, ...

        API->>Mod: check(answer)
        Mod->>LLM: complete_structured(prompt, ModerationResult)
        LLM-->>Mod: flagged, reason
        Mod-->>API: output_check

        opt output_check.flagged
            API->>API: replace answer with generic refusal
        end

        API->>DB: append_message(conversation_id, "user", query)
        API->>DB: append_message(conversation_id, "assistant", answer)
        API-->>Client: 200 AnswerResponse {conversation_id, answer, citations, ...}
    end
```
