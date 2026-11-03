// Paste one query at a time into http://127.0.0.1:17474/.
// Login uses connection.local.json; do not put credentials in this file.

// Active ontology coverage (older versions excluded).
MATCH (a:BOQOntologyActive {id:'boq-ontology'}), (n:BOQOntology)
WHERE n.dataset=a.version
RETURN n.kind AS kind, count(*) AS count ORDER BY kind;

// S001 and immediate evidence/relationships.
MATCH (a:BOQOntologyActive {id:'boq-ontology'}), (n:BOQOntology {id:'boq:S001'})
WHERE n.dataset=a.version
MATCH (n)-[r]-(m:BOQOntology)
RETURN n,r,m LIMIT 60;

// S031 has multiple observed UniFormat codes: do not collapse them.
MATCH (a:BOQOntologyActive {id:'boq-ontology'}), (n:BOQOntology {id:'boq:S031'})
WHERE n.dataset=a.version
MATCH (n)-[r:OBSERVED_AS]->(u:BOQOntology)
RETURN n.id,u.code,r.payload;

// Existing foundation conceptual graph, separate from reviewed mapping assertions.
MATCH (a:BOQOntologyActive {id:'boq-ontology'}), (n:BOQOntology)
WHERE n.dataset=a.version AND n.kind='FoundationEvidence'
MATCH (n)-[r:IS_A|PART_OF|GENERATES_WORK_ITEM]->(m)
RETURN n,r,m LIMIT 100;
