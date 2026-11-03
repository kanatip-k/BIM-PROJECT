"""Ontology integration contract: real Neo4j and real MCP subprocess required."""
import asyncio
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ontology_neo4j'))
from core import GraphStore, build_dataset, classify, external_mapping

@pytest.fixture(scope='module')
def snapshot():
    db=GraphStore()
    try:
        yield db.snapshot()
    finally:
        db.close()

def probe(category, uniformat, **props):
    return {'id':'probe','uniformatCode':uniformat,'boqEligible':True,'properties':{'Element.Category':category,**props}}

def codes(result):
    return {x['code'] for x in result['issues']}

def test_graph_coverage_and_import_idempotence(snapshot):
    d=build_dataset()
    assert d['version']==snapshot['version']
    assert sum(n['kind']=='WorkItem' for n in d['nodes'])==114
    assert Counter(x['matchStatus'] for x in snapshot['bundle']['eitMapping']['mappings'])=={'matched':75,'needs_review':25,'unresolved':14}
    db=GraphStore()
    try:
        db.import_dataset(d)
        db.import_dataset(d)
        assert db.query('MATCH (n:BOQOntology {dataset:$v}) RETURN count(n) AS count',v=d['version'])[0]['count']==len(d['nodes'])
        assert db.query('MATCH (n:BOQOntology {dataset:$v})-[r]->() RETURN count(r) AS count',v=d['version'])[0]['count']==len(d['edges'])
    finally:
        db.close()

def test_material_scope_and_foundation_guards(snapshot):
    for category, uniformat, concrete in [('Structural Columns','B1011','S005'),('Structural Framing','B1012','S006')]:
        e=probe(category,uniformat,**{'Element Properties.StructuralMaterialType':'Steel'})
        r=classify(e,'Structure','',snapshot)
        assert (r['element_code'],r['eit_cost_code'],r['quantity'])==('S031',None,None)
        assert 'EIT_COSTCODE_NEEDS_CONFIRMATION' in codes(r)
        e['properties']['Element Properties.StructuralMaterialType']='Concrete'
        assert classify(e,'Structure','',snapshot)['element_code']==concrete
        del e['properties']['Element Properties.StructuralMaterialType']
        assert 'STRUCTURAL_MATERIAL_TYPE_MISSING' in codes(classify(e,'Structure','',snapshot))
        assert 'DISCIPLINE_SCOPE_REQUIRED' in codes(classify(e,None,'',snapshot))
    slab=probe('Floors','A1010',**{'FloorType.IsFoundationSlab':'True'})
    assert classify(slab,'Structure','',snapshot)['element_code']=='S004'
    floor=probe('Floors','B1010')
    r=classify(floor,'Architecture','',snapshot)
    assert r['element_code'] is None and r['candidates']==['A008','A009','A010','A011']
    assert 'DISCIPLINE_SCOPE_CONFLICT' in codes(classify(floor,'Structure','CASE2_AR.nwc',snapshot))

def test_generic_acceptance_probes(snapshot):
    cases=[('S001','IfcFooting','PAD_FOOTING','Pad Footing','A1010','Structural Foundations'),
           ('S028','IfcPile','NOTDEFINED','Driven Precast Pile','A1030','Structural Foundations'),
           ('M045','System','','Testing Commissioning Balancing','D5090','Mechanical Equipment'),
           ('S031','IfcBeam','NOTDEFINED','Steel Beam','B1012','Structural Framing')]
    for code,entity,predef,name,uc,category in cases:
        e={'id':code,'display_name':name,'class_name':entity,'ifc_entity':entity,'ifc_predefined_type':predef,
           'uniformat_code':uc,'boq_eligible':True,'properties':{'Element.Category':category,'Element.Type':name}}
        r=classify(e,None,'PARITY_PROBES.nwc',snapshot)
        assert r['element_code']==code
        assert r['quantity'] is None and r['unit'] is None
        if code=='S001': assert r['eit_cost_code']=='1 1 03'
        if code=='S028': assert 'UNIT_BASIS_AMBIGUOUS' in codes(r)
        if code=='M045': assert 'MANUAL_LINE_ITEM_NOT_AUTO_COMPUTABLE' in codes(r)
        if code=='S031': assert r['eit_cost_code'] is None

def test_external_mapping_requires_review_and_keeps_ambiguity(snapshot):
    assert external_mapping(snapshot['bundle'],'S001','MASTERFORMAT')['status']=='not_loaded'
    # Deliberately synthetic tokens: never imported into the production graph.
    b={'external':{'classifications':[{'scheme':'MASTERFORMAT','code':'TEST-ONLY'}],
       'crosswalks':[{'element_code':'S001','scheme':'MASTERFORMAT','target_code':'TEST-ONLY','status':'needs_review'}]}}
    assert external_mapping(b,'S001','MASTERFORMAT')['code'] is None
    b['external']['crosswalks'][0]['status']='verified'
    assert external_mapping(b,'S001','MASTERFORMAT')['code']=='TEST-ONLY'
    b['external']['crosswalks'].append({'element_code':'S001','scheme':'MASTERFORMAT','target_code':'TEST-OTHER','status':'verified'})
    assert external_mapping(b,'S001','MASTERFORMAT')['code'] is None

def test_full_case2_parity_against_proven_crosswalk(snapshot):
    expected_hashes={'Structure':('CASE2_ST_ALL.boq.json','AD86B0EDE7C2732F25D622738422C7568EC45D96F1EBC6F972630669C2F72157'),
                     'Architecture':('CASE2_AR.boq.json','D2DA9FB646FA54D44EDC70237306B92468708E8B306C7F46188E702D51F0E768')}
    pair_counts=Counter()
    evidence_counts={}
    report={}
    for scope,(file,digest) in expected_hashes.items():
        path=ROOT/'data/export'/file
        assert hashlib.sha256(path.read_bytes()).hexdigest().upper()==digest, 'CASE2 source changed: parity invalid'
        payload=json.loads(path.read_text(encoding='utf-8'))
        tally=Counter()
        for e in payload['elements']:
            r=classify(e,scope,payload['modelName'],snapshot)
            tally.update(codes(r))
            if r['element_code']:
                tally['resolved']+=1
                pair_counts[(r['element_code'],r['uniformat_cost_code'])]+=1
                if e.get('properties',{}).get('Element.Category')=='Walls':
                    tally['wall_resolved']+=1
                    assert r['element_code']!='S008'
        assert tally['GROUP_NODE_EXCLUDED']==(5871 if scope=='Structure' else 8534)
        assert tally['resolved']==(3583 if scope=='Structure' else 1155)
        if scope=='Structure':
            assert tally['ELEMENT_TYPE_NOT_IN_SPEC']==80
            assert tally['TYPE_ABBREVIATION_UNCONFIRMED']==514
        report[scope]=dict(tally)
    audit=json.loads((ROOT/'docs/case2_cost_code_ground_truth.json').read_text(encoding='utf-8'))
    assert pair_counts==Counter({(r['elementCode'],r['uniformatCostCode']):r['totalCount'] for r in audit['crosswalk']})
    (ROOT/'ontology_neo4j/case2_mcp_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

def test_real_stdio_mcp_tools():
    async def run():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params=StdioServerParameters(command=str(ROOT/'ontology_neo4j/.venv/Scripts/python.exe'),args=[str(ROOT/'ontology_neo4j/server.py')],env={**os.environ,'PYTHONIOENCODING':'utf-8'})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                listed=await session.list_tools()
                assert len(listed.tools)==7
                for t in listed.tools:
                    assert t.annotations.model_dump(by_alias=True)['readOnlyHint']
                def payload(r):
                    assert not r.model_dump(by_alias=True)['isError'], str(r)
                    return json.loads(next(x.text for x in r.content if x.type=='text'))
                health=payload(await session.call_tool('ontology_health',{}))
                assert health['backend']=='Neo4j' and health['status']=='ready'
                cross=payload(await session.call_tool('resolve_crosswalk',{'element_code':'S031'}))
                assert cross['eit_cost_code'] is None
                assert {x['uniformat'] for x in cross['uniformat_observations']}=={'B1011','B1012'}
                assert payload(await session.call_tool('search_ontology',{'query':'S001','kind':'WorkItem'}))['results']
                assert payload(await session.call_tool('get_concept',{'concept_id':'boq:S001'}))['relations']
                assert payload(await session.call_tool('get_measurement_requirements',{'element_code':'S001'}))['requirements']
                e=probe('Structural Columns','B1011',**{'Element Properties.StructuralMaterialType':'Steel'})
                assert payload(await session.call_tool('classify_element',{'element':e,'scope':'Structure'}))['element_code']=='S031'
                assert payload(await session.call_tool('classify_elements',{'elements':[e,{'id':''}],'scope':'Structure'}))['resolved']==1
                assert (await session.call_tool('classify_elements',{'elements':[]})).model_dump(by_alias=True)['isError']
                assert not payload(await session.call_tool('search_ontology',{'query':"' MATCH (n) DETACH DELETE n //"}))['results']
    asyncio.run(run())

def test_mcp_database_failure_is_explicit_no_local_fallback():
    async def run():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params=StdioServerParameters(command=str(ROOT/'ontology_neo4j/.venv/Scripts/python.exe'),args=[str(ROOT/'ontology_neo4j/server.py')],
            env={**os.environ,'PYTHONIOENCODING':'utf-8','BOQ_NEO4J_URI':'bolt://127.0.0.1:1'})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                result=await session.call_tool('classify_element',{'element':probe('Doors','C1020'),'scope':'Architecture'})
                assert result.model_dump(by_alias=True)['isError']
                assert 'ONTOLOGY_DATABASE_UNAVAILABLE' in str(result)
    asyncio.run(run())
