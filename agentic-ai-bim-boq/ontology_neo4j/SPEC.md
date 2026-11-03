# BOQ Ontology MCP

Implement the user's agreed three-MCP architecture using the existing Python MCP SDK.
This server is a read-only stdio tool service for Claude Desktop. Neo4j is the required
knowledge backend, not an optional cache. No Skybridge UI or pricing implementation.

Use the 114 existing work items, EIT hierarchy/statuses, measurement rules, field roles,
CASE2 observed crosswalk, candidate buckets and foundation ontology. Keep original sources
unchanged. A graph dataset has content hashes and immutable version; activate only after
one successful atomic import. Import is an administrator CLI, never an LLM tool.

Knowledge nodes and typed edges encode work items, construction concepts, classification
codes, measurement rules, fields, sources and project rules. Imported JSON preserves all
details. EIT matched is a project mapping status, not expert approval. Observed UNIFORMAT
crosswalks are empirical output, not one-to-one equivalences. MasterFormat/OmniClass have
explicit pending schemes; no unverified mappings are invented.

Tools: health, search concepts, concept details, crosswalk, measurement rule,
classify element/batch, evidence validation, graph neighborhood. Read-only parameterized
queries only. Keep existing classifier behavior via an adapter with pinned code hashes.
Guard group nodes, structural walls, unresolved EIT and ambiguous floors. Reject conflicting
scope; preserve raw classification evidence. No prices or inferred quantity calculations.

Tests: baseline existing suite, pure graph construction, guard probes, real Neo4j import
and read, full CASE2 resolved counts, MCP stdio discovery/calls, unavailable-backend behavior.
