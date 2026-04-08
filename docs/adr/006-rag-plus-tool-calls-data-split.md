# ADR 006: RAG + Tool Calls Data Split

## Status

Deferred (planned for M2)

## Context

The advisor agent needs two kinds of data:

1. **Structured fund data** (NAV, expense ratio, AUM, category) -- well-suited for tool calls returning typed objects.
2. **Unstructured fund knowledge** (AMC commentary, fund manager interviews, factsheet narratives, investment philosophy explanations) -- better served by RAG retrieval.

Currently, only structured data is available via mfdata.in tool calls. The agent generates rationale from its training knowledge, which is acceptable but not grounded in current fund-specific context.

## Decision

When implemented in M2:

- **Tool calls** handle structured queries: fund search, NAV lookup, performance comparison. These return `MutualFund` Pydantic objects.
- **RAG** handles unstructured context: fund factsheets, AMC reports, and the InertExpert2911 dataset's descriptive fields. Retrieved text is injected into the user message as context.

The split is: tools for precise lookups, RAG for narrative context.

## Consequences

- **Positive**: Each data access pattern uses the right mechanism. Tools give structured, parseable data. RAG gives rich context without needing to model every field.
- **Positive**: RAG context can improve rationale quality without changing the advisor's output schema.
- **Negative**: RAG adds embedding/retrieval infrastructure (vector store, chunking, embedding model). Adds complexity relative to tool-only approach.
- **Negative**: RAG context in the prompt increases token usage and cost per run.
