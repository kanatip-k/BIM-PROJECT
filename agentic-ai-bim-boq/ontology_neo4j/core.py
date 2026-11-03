"""Versioned Neo4j knowledge store and conservative BOQ classification adapter."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get('BOQ_PROJECT_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / 'python_app'))
from boq_workflow import pipeline as p
from boq_workflow.service import _pipeline_input


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_dataset(root=ROOT):
    config = root / 'python_app/boq_workflow/config'
    names = {'elementRules': 'boq_element_rules.json', 'eitMapping': 'boq_to_eit_mapping.json',
             'eitReference': 'eit_cost_code_reference.json', 'mapping': 'mapping_rules.json',
             'measurement': 'measurement_rules.json', 'fieldRoles': 'field_roles.json'}
    sources = [config / name for name in names.values()] + [
        root / 'docs/case2_cost_code_ground_truth.json',
        root / 'ontology_neo4j/foundation_ontology_base.json',
        root / 'python_app/boq_workflow/pipeline.py',
        root / 'python_app/boq_workflow/service.py',
        root / 'ontology_neo4j/external_classifications.json',
        root / 'ontology_neo4j/core.py', root / 'ontology_neo4j/server.py']
    audit_documents = [root / name for name in (
        'docs/nwc_property_inventory/MASTERFORMAT_CHECK_TH.md',
        'docs/nwc_property_inventory/WALL_OMNICLASS_AUDIT_TH.md',
        'docs/architecture_floor_types.md', 'docs/SPATIAL_EXPORT_STATUS_TH.md',
        'docs/model_readiness_20261003/REPORT_TH.md')]
    native_audit_path = root / 'docs/nwc_property_inventory/WALL_OMNICLASS_AUDIT.json'
    sources.extend(audit_documents + [native_audit_path])
    hashes = {str(x.relative_to(root)).replace('\\', '/'): sha(x) for x in sources}
    version = hashlib.sha256(encode(hashes).encode()).hexdigest()
    bundle = {k: json.loads((config / v).read_text(encoding='utf-8-sig')) for k, v in names.items()}
    bundle['external'] = json.loads((root / 'ontology_neo4j/external_classifications.json').read_text(encoding='utf-8-sig'))
    nodes, edges = {}, []

    def node(id, kind, data):
        nodes[id] = {'id': id, 'kind': kind, 'title': data.get('elementWorkItem') or data.get('nameTh') or data.get('name') or data.get('title') or id,
                     'code': data.get('code', ''), 'scheme': data.get('scheme', ''),
                     'payload': encode(data), 'search': encode(data).casefold()}
        return id

    def edge(a, rel, b, data=None):
        edges.append({'from': a, 'type': rel, 'to': b, 'payload': encode(data or {})})

    for name, digest in hashes.items():
        node('source:' + name, 'Source', {'path': name, 'sha256': digest})
    for path in audit_documents:
        relative = path.relative_to(root).as_posix()
        aid = node('audit:' + path.stem, 'AuditDocument', {'name':path.stem, 'content':path.read_text(encoding='utf-8-sig'),
                    'status':'historical_audit_not_crosswalk', 'path':relative})
        edge(aid, 'SOURCED_FROM', 'source:' + relative)
    native = json.loads(native_audit_path.read_text(encoding='utf-8-sig'))
    for scope_row in native['omniAudit']:
        for i, pair in enumerate(scope_row['pairs']):
            aid = node('native-observation:' + scope_row['scope'] + ':' + str(i), 'NativeClassificationObservation',
                {**pair, 'scope':scope_row['scope'], 'source_hashes':native['sources'],
                 'mapping_status':'observed_not_verified_crosswalk'})
            edge(aid, 'SOURCED_FROM', 'source:docs/nwc_property_inventory/WALL_OMNICLASS_AUDIT.json')
    for name in ('UNIFORMAT', 'EIT', 'MASTERFORMAT', 'OMNICLASS'):
        node('scheme:' + name, 'Scheme', {'scheme': name, 'status': 'not_loaded' if name in ('MASTERFORMAT', 'OMNICLASS') else 'project_sources',
             'edition': 'unverified' if name != 'EIT' else bundle['eitReference']['version']})
    for field in bundle['elementRules']['dataDictionary']:
        node('field:' + field['fieldName'], 'Field', {**field, 'role': bundle['fieldRoles']['fieldRoles'][field['fieldName']],
             'observed_aliases': p.EVIDENCE_FIELD_ALIASES.get(field['fieldName'], ()),
             'alias_note': p.EVIDENCE_FIELD_ALIAS_NOTES.get(field['fieldName'])})
    for scope, rules in bundle['elementRules']['elementRules'].items():
        node('discipline:' + scope, 'Discipline', {'name': scope})
        for rule in rules:
            code = rule['code']
            node('boq:' + code, 'WorkItem', {**rule, 'discipline': scope})
            node('measurement:' + code, 'MeasurementRule', rule)
            edge('boq:' + code, 'IN_DISCIPLINE', 'discipline:' + scope)
            edge('boq:' + code, 'MEASURED_BY', 'measurement:' + code)
            edge('boq:' + code, 'SOURCED_FROM', 'source:python_app/boq_workflow/config/boq_element_rules.json')
            for field in rule['requiredFields']:
                edge('boq:' + code, 'REQUIRES_FIELD', 'field:' + field)
    for row in bundle['eitMapping']['mappings']:
        mapping = node('eit-mapping:' + row['code'], 'MappingAssertion', row)
        edge('boq:' + row['code'], 'HAS_MAPPING', mapping)
        if row.get('eitSubGroupCode'):
            code = row['eitSubGroupCode']
            node('eit:' + code, 'ClassificationCode', {'code': code, 'scheme': 'EIT'})
            edge(mapping, 'TARGETS', 'eit:' + code)
        edge(mapping, 'SOURCED_FROM', 'source:python_app/boq_workflow/config/boq_to_eit_mapping.json')
    for division in bundle['eitReference']['divisions']:
        did = node('eit-division:' + division['code'], 'ClassificationCode', {**division, 'scheme': 'EIT'})
        for group in division['groups']:
            gid = node('eit-group:' + division['code'] + ':' + group['code'], 'ClassificationCode', {**group, 'scheme': 'EIT'})
            edge(gid, 'IS_A', did)
            for subgroup in group.get('subGroups', []):
                if isinstance(subgroup, dict):
                    sid = node('eit:' + subgroup['code'], 'ClassificationCode', {**subgroup, 'scheme': 'EIT'})
                    edge(sid, 'IS_A', gid)
                    continue
                match = re.match(r'^(\d+\s+\d+\s+\d+)\s+(.+)$', subgroup)
                if match:
                    sid = node('eit:' + match[1], 'ClassificationCode', {'code': match[1], 'nameTh': match[2], 'scheme': 'EIT'})
                    edge(sid, 'IS_A', gid)
    audit = json.loads(sources[6].read_text(encoding='utf-8-sig'))
    for row in audit['crosswalk']:
        uid = node('uniformat:' + row['uniformatCostCode'], 'ClassificationCode', {'code': row['uniformatCostCode'], 'scheme': 'UNIFORMAT', 'edition': 'unverified'})
        edge('boq:' + row['elementCode'], 'OBSERVED_AS', uid, {**row, 'status': 'observed_pipeline_output', 'sources': audit['sources']})
    for (scope, code, category), candidates in p.CASE2_UNIFORMAT_CANDIDATES.items():
        uid = 'uniformat:' + code
        if uid not in nodes:
            node(uid, 'ClassificationCode', {'code': code, 'scheme': 'UNIFORMAT', 'edition': 'unverified'})
        for candidate in candidates:
            edge(uid, 'CANDIDATE_FOR', 'boq:' + candidate, {'scope': scope, 'category': category, 'status': 'candidate_not_equivalence'})
    for rule in bundle['elementRules'].get('projectRules', []):
        node('project-rule:' + rule['ruleId'], 'ProjectRule', rule)
    foundation = json.loads(sources[7].read_text(encoding='utf-8-sig'))
    for n in foundation['nodes']:
        node('foundation:' + n['id'], 'FoundationEvidence', {**n['properties'], 'original_labels': n['labels'], 'source_status': foundation['status']})
        if n['id'].startswith('boq:') and n['id'] in nodes:
            edge('foundation:' + n['id'], 'DESCRIBES', n['id'])
    for e in foundation['relationships']:
        edge('foundation:' + e['from'], e['type'], 'foundation:' + e['to'], e['properties'])
    external = bundle['external']
    registered = set()
    for row in external['classifications']:
        if row.get('scheme') not in ('MASTERFORMAT', 'OMNICLASS') or not all(row.get(k) for k in ('code','title','edition','source')):
            raise ValueError('External catalog requires scheme, code, title, edition and source')
        key = (row['scheme'], row['code'])
        if key in registered:
            raise ValueError('Duplicate external catalog code')
        registered.add(key)
        node('external:' + ':'.join(key), 'ClassificationCode', row)
        node('scheme:' + row['scheme'], 'Scheme', {'scheme':row['scheme'], 'status':'project_catalog_loaded', 'edition':row['edition']})
    for index, row in enumerate(external['crosswalks']):
        if row.get('status') not in ('verified','needs_review','unresolved') or row.get('element_code') not in {r['code'] for rs in bundle['elementRules']['elementRules'].values() for r in rs}:
            raise ValueError('Invalid external crosswalk status or element code')
        if (row.get('scheme'), row.get('target_code')) not in registered or not row.get('source'):
            raise ValueError('External crosswalk must reference a catalog entry and source')
        if row['status']=='verified' and not all(row.get(k) for k in ('reviewed_by','reviewed_on')):
            raise ValueError('Verified crosswalk requires reviewer and review date')
        if row.get('scope') not in (None,'Structure','Architecture','MEP'):
            raise ValueError('Invalid crosswalk scope')
        mid=node('external-mapping:' + str(index), 'MappingAssertion', row)
        edge('boq:' + row['element_code'], 'HAS_EXTERNAL_MAPPING', mid)
        edge(mid, 'TARGETS', 'external:' + row['scheme'] + ':' + row['target_code'])
    for n in nodes.values():
        if n['kind']=='ClassificationCode' and n['scheme']:
            edge(n['id'], 'IN_SCHEME', 'scheme:' + n['scheme'])
    for e in edges:
        if e['from'] not in nodes or e['to'] not in nodes:
            raise ValueError(f'Dangling ontology relation: {e}')
    return {'version': version, 'hashes': hashes, 'bundle': bundle, 'nodes': list(nodes.values()), 'edges': edges}


class GraphStore:
    def __init__(self):
        from neo4j import GraphDatabase
        settings = Path(__file__).with_name('connection.local.json')
        cfg = json.loads(settings.read_text(encoding='utf-8-sig')) if settings.exists() else {}
        self.database = os.environ.get('BOQ_NEO4J_DATABASE', cfg.get('database', 'neo4j'))
        password = os.environ.get('BOQ_NEO4J_PASSWORD', cfg.get('password'))
        if not password:
            raise RuntimeError('NEO4J_NOT_CONFIGURED: set BOQ_NEO4J_PASSWORD or connection.local.json')
        self.driver = GraphDatabase.driver(os.environ.get('BOQ_NEO4J_URI', cfg.get('uri', 'bolt://127.0.0.1:17687')),
            auth=(os.environ.get('BOQ_NEO4J_USER', cfg.get('user', 'neo4j')), password),
            connection_timeout=5, max_transaction_retry_time=5)

    def close(self):
        self.driver.close()

    def query(self, query, **params):
        records, _, _ = self.driver.execute_query(query, parameters_=params, database_=self.database, routing_='r')
        return [r.data() for r in records]

    def import_dataset(self, dataset):
        self.driver.verify_connectivity()
        self.driver.execute_query('CREATE CONSTRAINT boq_ontology_identity IF NOT EXISTS FOR (n:BOQOntology) REQUIRE (n.dataset, n.id) IS UNIQUE', database_=self.database)
        def write(tx):
            version = dataset['version']
            tx.run('UNWIND $nodes AS row MERGE (n:BOQOntology {dataset:$v,id:row.id}) SET n += row', nodes=dataset['nodes'], v=version).consume()
            types = sorted({e['type'] for e in dataset['edges']})
            for rel in types:
                if not re.fullmatch('[A-Z_]+', rel):
                    raise ValueError('Invalid relation type')
                rows = [dict(e, index=i) for i, e in enumerate(dataset['edges']) if e['type'] == rel]
                tx.run(f'UNWIND $rows AS row MATCH (a:BOQOntology {{dataset:$v,id:row.from}}), (b:BOQOntology {{dataset:$v,id:row.to}}) MERGE (a)-[r:{rel} {{edge_index:row.index}}]->(b) SET r.payload=row.payload', rows=rows, v=version).consume()
            tx.run('MERGE (d:BOQOntologyDataset {version:$v}) SET d.bundle=$bundle,d.hashes=$hashes,d.node_count=$nc,d.edge_count=$ec MERGE (a:BOQOntologyActive {id:"boq-ontology"}) SET a.version=$v',
                   v=version, bundle=encode(dataset['bundle']), hashes=encode(dataset['hashes']), nc=len(dataset['nodes']), ec=len(dataset['edges'])).consume()
        with self.driver.session(database=self.database) as session:
            session.execute_write(write)

    def snapshot(self):
        rows = self.query('MATCH (a:BOQOntologyActive {id:"boq-ontology"}), (d:BOQOntologyDataset) WHERE d.version=a.version RETURN properties(d) AS d')
        if not rows:
            raise RuntimeError('ONTOLOGY_NOT_IMPORTED: run import_graph.py first')
        data = rows[0]['d']
        data['bundle'] = json.loads(data['bundle'])
        data['hashes'] = json.loads(data['hashes'])
        for rel in ('python_app/boq_workflow/pipeline.py','python_app/boq_workflow/service.py','ontology_neo4j/core.py','ontology_neo4j/server.py'):
            if sha(ROOT / rel) != data['hashes'][rel]:
                raise RuntimeError('RULE_VERSION_CHANGED: rerun tests and import_graph.py')
        return data

    def neighborhood(self, version, id):
        rows = self.query('MATCH (n:BOQOntology {dataset:$v,id:$id}) OPTIONAL MATCH (n)-[r]-(m:BOQOntology {dataset:$v}) RETURN n.payload AS node, type(r) AS relation, r.payload AS evidence, m.id AS neighbor_id, m.payload AS neighbor LIMIT 250', v=version, id=id)
        return [{'node': json.loads(r['node']), 'relation': r['relation'], 'evidence': json.loads(r['evidence']) if r['evidence'] else None,
                 'neighbor_id': r['neighbor_id'], 'neighbor': json.loads(r['neighbor']) if r['neighbor'] else None} for r in rows]


def external_mapping(bundle, element_code, scheme, scope=None):
    catalog=[r for r in bundle.get('external',{}).get('classifications',[]) if r['scheme']==scheme]
    rows=[r for r in bundle.get('external',{}).get('crosswalks',[]) if r['element_code']==element_code and r['scheme']==scheme and (not r.get('scope') or r['scope']==scope)]
    verified={r['target_code'] for r in rows if r['status']=='verified'}
    return {'code':next(iter(verified)) if len(verified)==1 else None,
            'status':'verified' if len(verified)==1 else ('needs_confirmation' if rows else ('no_mapping' if catalog else 'not_loaded')),
            'assertions':rows}


def classify(element, scope, model, snapshot):
    bundle = snapshot['bundle']
    raw = _pipeline_input(element) if any(k in element for k in ('displayName', 'classDisplayName', 'uniformatCode')) else dict(element)
    raw['properties'] = {k: p._normal(v) for k, v in (raw.get('properties') or {}).items()}
    props = raw['properties']
    result = {'element_id': raw.get('id'), 'element_code': None, 'eit_cost_code': None,
              'uniformat_cost_code': None, 'masterformat_cost_code': None, 'candidates': [],
              'ontology_version': snapshot['version'], 'issues': [], 'quantity': None, 'unit': None,
              'classification_evidence': raw.get('classification_evidence'),
              'scope': scope, 'measurement': None, 'evidence': props,
              'limitations': ['Classification is not a priced or quantified BOQ line']}
    def issue(code):
        result['issues'].append({'code': code})
    if not p._normal(raw.get('id')) or not p._normal(props.get('Element.Category')):
        issue('GROUP_NODE_EXCLUDED')
        return result
    if not p._is_eligible(raw):
        issue('ELEMENT_NOT_BOQ_ELIGIBLE')
        return result
    inferred = p._case2_scope(model)
    if scope and inferred and scope != inferred:
        issue('DISCIPLINE_SCOPE_CONFLICT')
        return result
    scope = scope or inferred
    result['scope'] = scope
    if p._is_unconfirmed_structural_wall(raw):
        issue('ELEMENT_TYPE_NOT_IN_SPEC' if p._is_structural_curb(raw) else 'TYPE_ABBREVIATION_UNCONFIRMED')
        return result
    # Native-only input without scope cannot safely choose ST vs AR candidate buckets.
    explicit_ifc = raw.get('ifc_entity') or re.search(r'\bIfc[A-Za-z]+\b', str(raw.get('class_name', '')))
    if not scope and not explicit_ifc and 'commission' not in str(raw).casefold():
        issue('DISCIPLINE_SCOPE_REQUIRED')
        return result
    match = p._match_element_rule(raw, bundle['elementRules'], scope)
    code = match['element_code']
    uniformat, _, source = p._cost_code(raw, bundle['mapping'])
    result.update(element_code=code, candidates=match['element_rule_candidates'],
                  uniformat_cost_code=None if uniformat == 'UNCLASSIFIED' else uniformat,
                  match_source=match.get('element_match_source'), uniformat_source=source)
    if not code:
        issue(match.get('element_match_issue_code') or 'NO_ELEMENT_RULE_MATCH')
        return result
    mapping = next((r for r in bundle['eitMapping']['mappings'] if r['code'] == code), None)
    result['eit_mapping_evidence'] = mapping
    external = external_mapping(bundle, code, 'MASTERFORMAT', scope)
    result['masterformat_cost_code'] = external['code']
    result['masterformat_mapping'] = external
    if mapping and mapping['matchStatus'] == 'matched':
        result['eit_cost_code'] = mapping['eitSubGroupCode']
    else:
        issue('EIT_COSTCODE_NEEDS_CONFIRMATION')
    if match.get('element_match_source') == 'element-keyword-fallback':
        issue('ELEMENT_CODE_FROM_KEYWORD_FALLBACK')
    rule = match['element_rule']
    result['measurement'] = p._measurement_rule({**raw, **match}, match['element_discipline'], bundle['measurement'])
    result['required_field_audit'] = p._required_field_audit(raw, rule, model, bundle['fieldRoles'])
    if result['required_field_audit']['missingFields']:
        result['issues'].append({'code': 'REQUIRED_FIELD_MISSING', 'fields': result['required_field_audit']['missingFields']})
    if code == 'S028':
        issue('UNIT_BASIS_AMBIGUOUS')
    if code == 'M045':
        issue('MANUAL_LINE_ITEM_NOT_AUTO_COMPUTABLE')
    if result['measurement']['measure'] == 'WEIGHT':
        issue('WEIGHT_UNIT_UNVERIFIED')
    result['unit'] = None  # No quantities are computed by this classification service.
    return result
