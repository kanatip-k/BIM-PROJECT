"""Read-only CASE2 wall evidence / Category-OmniClass audit; never changes rules."""
from pathlib import Path
from collections import Counter, defaultdict
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python_app'))
from boq_workflow.pipeline import run_pipeline
from boq_workflow.configuration import load_bundle
from boq_workflow.service import _pipeline_input

EXPECTED_TITLES = {
    'Structural Columns': {'Columns'},
    'Structural Framing': {'Beams'},
    'Doors': {'Doors'},
    'Windows': {'Windows'},
}

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest().upper()


def audit():
    report = {'wallAudit': None, 'omniAudit': [], 'sources': [],
              'comparisonPolicy': 'Observed CASE2 categories compared to exact expected native titles; unknown categories/titles are reported unassessed, never silently matched. Family/Type duplicate evidence counted once per instance. No code/title standards validation or cost-code decision.'}
    prior = json.loads((ROOT/'docs/nwc_property_inventory/native_classification_export_summary.json').read_text(encoding='utf-8'))
    expected_hashes = {r['scope']: r['snapshotSha256'] for r in prior}
    for scope, name in [('Structure', 'CASE2_ST_ALL'), ('Architecture', 'CASE2_AR')]:
        path = ROOT / 'data/export' / (name + '.classified-source.json')
        assert sha(path) == expected_hashes[scope], 'Enriched CASE2 source changed; re-audit export provenance before comparing results'
        payload = json.loads(path.read_text(encoding='utf-8'))
        report['sources'].append({'scope':scope, 'file':str(path), 'sha256':sha(path)})
        if scope == 'Structure':
            result = run_pipeline(payload['modelName'], [_pipeline_input(e) for e in payload['elements']], load_bundle())
            walls = [e for e in result['classifiedElements'] if e.get('excluded_reason') == 'TYPE_ABBREVIATION_UNCONFIRMED']
            assert len(walls) == 514
            assert all(e.get('element_code') is None for e in walls)
            by_type = defaultdict(list)
            for e in walls:
                by_type[e['properties'].get('Element.Type','')].append(e)
            types = []
            for name_type, items in sorted(by_type.items()):
                values = Counter((r['propertyKey'],r['value']) for e in items for r in e['classification_evidence']['nativeProperties'])
                types.append({'type':name_type,'elementCount':len(items),
                    'withNativeEvidence':sum(bool(e['classification_evidence']['nativeProperties']) for e in items),
                    'nativeValues':[{'propertyKey':k,'value':v,'count':n} for (k,v),n in sorted(values.items())],
                    'exampleIds':[e['id'] for e in items[:3]]})
            report['wallAudit'] = {'total':len(walls),'types':types,
                'withNativeEvidence':sum(bool(e['classification_evidence']['nativeProperties']) for e in walls),
                's008Count':sum(e.get('element_code')=='S008' for e in result['classifiedElements'] if e['properties'].get('Element.Category')=='Walls'),
                'all514ElementIds':[e['id'] for e in walls]}
            del result
        pairs = Counter()
        status_counts = Counter()
        conflicts = defaultdict(list)
        missing_category_pairs = Counter()
        all_omni_nodes = 0
        valid_ids = []
        internal_conflicts = []
        native_instances = 0
        valid_instances = 0
        for e in payload['elements']:
            ev = e['classificationEvidence']['nativeProperties']
            identified = bool(e.get('id')) and bool(e['properties'].get('Element.Category'))
            if identified:
                valid_instances += 1
                native_instances += bool(ev)
            numbers = {r['value'] for r in ev if r['propertyKey'].endswith('OmniClass Number')}
            titles = {r['value'] for r in ev if r['propertyKey'].endswith('OmniClass Title')}
            if not numbers and not titles: continue
            all_omni_nodes += 1
            category = e['properties'].get('Element.Category','')
            pair = (category,tuple(sorted(numbers)),tuple(sorted(titles)))
            if not identified:
                missing_category_pairs[pair] += 1
                continue
            valid_ids.append(e['id'])
            if len(numbers)>1 or len(titles)>1:
                internal_conflicts.append({'id':e['id'],'numbers':sorted(numbers),'titles':sorted(titles)})
            if category not in EXPECTED_TITLES or not titles:
                status = 'unassessed'
            elif titles.issubset(EXPECTED_TITLES[category]):
                status = 'consistent'
            else:
                status = 'conflict'
            pairs[(pair,status)] += 1
            status_counts[status] += 1
            if status == 'conflict':
                conflicts[pair].append({'id':e['id'],'family':e['properties'].get('Element.Family'),
                    'type':e['properties'].get('Element.Type'),'ancestorPath':e['ancestorPath'],
                    'nativeEvidence':[r for r in ev if 'OmniClass' in r['propertyKey']]})
        assert len(valid_ids) == len(set(valid_ids)), 'Duplicate IDs would invalidate element counts'
        def pair_row(pair,count):
            c,n,t=pair
            return {'category':c,'numbers':list(n),'titles':list(t),'elementCount':count}
        report['omniAudit'].append({'scope':scope,'exportedNodes':len(payload['elements']),
            'identifiedCategorizedInstances':valid_instances,'instancesWithAnyNativeEvidence':native_instances,
            'allExportNodesWithOmniClass':all_omni_nodes,'instancesWithOmniClass':len(valid_ids),
            'omniCoveragePercent':round(100*len(valid_ids)/valid_instances,2),
            'consistent':status_counts['consistent'],'conflict':status_counts['conflict'],
            'unassessed':status_counts['unassessed'],
            'conflictPercentAmongOmniInstances':round(100*status_counts['conflict']/len(valid_ids),2),
            'pairs':[dict(pair_row(pair,count),status=status) for (pair,status),count in sorted(pairs.items())],
            'excludedUncategorizedOrUnidentifiedOmniNodes':sum(missing_category_pairs.values()),
            'excludedPairs':[pair_row(pair,count) for pair,count in sorted(missing_category_pairs.items())],
            'familyTypeDisagreements':internal_conflicts,
            'conflicts':[dict(pair_row(pair,len(items)),types=[{'type':t,'count':n} for t,n in sorted(Counter(e['type'] for e in items).items())],elements=items) for pair,items in sorted(conflicts.items())]})
        del payload
    folder = ROOT/'docs/nwc_property_inventory'
    (folder/'WALL_OMNICLASS_AUDIT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    wall = report['wallAudit']
    lines = ['# ตรวจผนังที่ค้างและ Category–OmniClass จาก export ใหม่', '', 'วันที่: 3 ตุลาคม 2026', '',
        'อ่าน CASE2_ST_ALL.classified-source.json และ CASE2_AR.classified-source.json ทั้งไฟล์; ใช้ผล CLASSIFY ของโค้ดปัจจุบันระบุผนังที่ excluded_reason=TYPE_ABBREVIATION_UNCONFIRMED เท่านั้น ไม่ใช้การเดาจากตัวย่อ. ไม่แก้ CLASSIFY, rulebook หรือ pricing.', '',
        '## 1. ผนัง 514 ตัว', '',
        f"ผนังที่ค้าง {wall['total']} ตัว / {len(wall['types'])} Type มี native Assembly Code/Description, OmniClass Number/Title หรือ Keynote เพิ่ม **{wall['withNativeEvidence']} ตัว (0%)**. ไม่มีตัวใดอยู่ในกลุ่ม Structure 1,479 ตัวที่มี native evidence. S008 ยังเป็น 0 ตัว.", '',
        '| Element.Type จริง | จำนวน | มี native evidence | Assembly Code/Description | OmniClass Number/Title | Keynote |',
        '|---|---:|---:|---|---|---|']
    for row in wall['types']:
        assert not row['nativeValues'], 'Update rendering and review new wall evidence before reporting none'
        lines.append(f"| {row['type']} | {row['elementCount']} | {row['withNativeEvidence']} | ไม่พบ | ไม่พบ | ไม่พบ |")
    lines += ['', '**ข้อเสนอ:** ไม่มีหลักฐานใหม่ช่วยแยกงานผนังได้ จึงยังต้องรอ glossary/แบบ ST/ทีมโมเดล. ไม่มีข้อเสนอให้ย้าย LB/SW/WR/WTB หรือชื่ออื่นไป S008 จากข้อมูลรอบนี้ และไม่อนุมานความหมายของตัวย่อ.', '',
        '## 2. Category–OmniClass ทุก element', '',
        'นับ element ที่มี id และ Element.Category โดยนับคู่ Family/Type ที่ซ้ำกันเพียงครั้งเดียวต่อ element. Expected pairs ใช้เฉพาะหมวดที่พบจริง: Structural Columns↔Columns, Structural Framing↔Beams, Doors↔Doors, Windows↔Windows. Title ไม่ตรงกลุ่มเป็น conflict; ถ้าประเมินไม่ได้ต้องรายงาน unassessed. การตรงของชื่อกลุ่มไม่พิสูจน์ว่า code หรือ classification เชิงวิศวกรรมถูกทั้งหมด.', '',
        '| Scope | Element มี OmniClass | ตรงกลุ่ม | ขัดแย้ง | ประเมินไม่ได้ | ขัดแย้ง/มี OmniClass | OmniClass coverage ของ id+Category |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for row in report['omniAudit']:
        lines.append(f"| {row['scope']} | {row['instancesWithOmniClass']} | {row['consistent']} | {row['conflict']} | {row['unassessed']} | {row['conflictPercentAmongOmniInstances']}% | {row['omniCoveragePercent']}% |")
    lines += ['', '| Scope | Category | OmniClass Number | OmniClass Title | จำนวน element | ผล |', '|---|---|---|---|---:|---|']
    for row in report['omniAudit']:
        for pair in row['pairs']:
            lines.append(f"| {row['scope']} | {pair['category']} | {', '.join(pair['numbers'])} | {', '.join(pair['titles'])} | {pair['elementCount']} | {pair['status']} |")
    lines += ['', '### ทุก Type ในคู่ที่ขัดแย้ง', '', '| Scope | Category | OmniClass Title | Element.Type | จำนวน |','|---|---|---|---|---:|']
    for row in report['omniAudit']:
        for conflict in row['conflicts']:
            for type_row in conflict['types']:
                lines.append(f"| {row['scope']} | {conflict['category']} | {', '.join(conflict['titles'])} | {type_row['type']} | {type_row['count']} |")
    total=sum(row['instancesWithOmniClass'] for row in report['omniAudit'])
    bad=sum(row['conflict'] for row in report['omniAudit'])
    lines += ['', f"รวมขัดแย้ง {bad}/{total} = {100*bad/total:.2f}%. พบคู่ที่ขัดแย้งเดียวคือ Doors→Climate Control (HVAC) แต่ครอบคลุม 5 Type ไม่ใช่ Lift3 เพียงชื่อเดียว. Family/Type ไม่พบค่าต่างกันใน element เดียว. ข้อมูลชื่อ Type เป็นหลักฐานเพื่อให้ทีมโมเดลทบทวน ไม่ถือว่า Category ถูกกว่า OmniClass หรือใช้แก้ code อัตโนมัติ.", '',
        '### Nodes ที่มี OmniClass แต่ไม่มี Category/ไม่มี id', '',
        'สแกนรวมแล้ว แต่ไม่ใช้เป็น element ในตัวหารความขัดแย้งเพราะเทียบ Category ไม่ได้ และต้องไม่เพิ่มกลับเข้า BOQ:', '',
        '| Scope | Export nodes มี OmniClass ทั้งหมด | Node ไม่มี Category/id | OmniClass Title | จำนวน nodes |',
        '|---|---:|---:|---|---:|']
    for row in report['omniAudit']:
        for pair in row['excludedPairs']:
            lines.append(f"| {row['scope']} | {row['allExportNodesWithOmniClass']} | {row['excludedUncategorizedOrUnidentifiedOmniNodes']} | {', '.join(pair['titles'])} | {pair['elementCount']} |")
    lines += ['', '## ข้อเสนอให้ผู้ใช้ตัดสินใจ', '',
        '- ผนัง: คง guard และรอ glossary เพราะ native evidence ไม่เพิ่มข้อมูลให้ทั้ง 514 ตัว',
        '- OmniClass: ใช้เป็นสัญญาณเสริมในหมวดที่ตรวจผ่านได้; ก่อนเพิ่มน้ำหนักให้เป็นสัญญาณหลักรอง UNIFORMAT ให้ทีมโมเดลยืนยันกลุ่ม lift/HVAC และ crosswalk ก่อน. คู่ที่ตรงกันเป็นการตรวจความสอดคล้องของ Category–Title ไม่ใช่ ground truth ทั้งมาตรฐาน',
        '- Coverage ต่ำ (Structure 29.39%, Architecture 4.71% ของ id+Category) จึงใช้แทน Layer 0 หรือจัดหมวดทุก element ไม่ได้ แม้ความขัดแย้งจะกระจุกอยู่คู่เดียว',
        '- Architecture Floors: ยังค้างรอการตัดสินใจตาม docs/architecture_floor_types.md ไม่เพิ่ม vocabulary หรือ map A008–A011 ในรอบนี้', '',
        '## หลักฐาน', '', 'WALL_OMNICLASS_AUDIT.json เก็บ SHA-256 ของ export ทั้งสองไฟล์, ID ของผนังครบ 514 ตัว, ตัวอย่าง ID ต่อ Type, ตารางคู่ครบ และ ID/source paths/native evidence ของ conflict ทั้ง 81 ตัว เพื่อย้อนตรวจราย element ได้.']
    (folder/'WALL_OMNICLASS_AUDIT_TH.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'wallTotal':wall['total'],'wallTypeCount':len(wall['types']),'wallsWithNativeEvidence':wall['withNativeEvidence'],'omni':[{k:v for k,v in r.items() if k in {'scope','instancesWithOmniClass','conflict','consistent','unassessed','omniCoveragePercent'}} for r in report['omniAudit']]},ensure_ascii=False))

if __name__ == '__main__':
    audit()
