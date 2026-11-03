from pathlib import Path
from collections import Counter
import hashlib
import json
import math

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/nwc_property_inventory'
MODELS={
    'ST':ROOT/'data/CASE2_ST_ALL.nwc',
    'AR':Path(r'D:\BIM-PROJECT\Case Study\Case2\01_ARCHITECTURE\02_NWC\CASE2_AR.nwc'),
}
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest().upper()

def cell(value):
    return str(value).replace('|','\\|').replace('\n',' ')

lines=['# ผลตรวจ classification properties จาก NWC โดยตรง', '',
    'วันที่ตรวจ: 3 ตุลาคม 2026', '',
    'อ่านผ่าน Navisworks .NET API แบบ NoGui ทุก node รวม root/category/Family/Type/instance/geometry ไม่ใช้ BOQ filter และไม่ใช้ UniformatClassifier ระหว่าง inventory', '',
    'ทั้ง Structure และ Architecture เปิด/ตรวจสำเร็จด้วย exit code 0 หลังผู้ใช้เข้าสู่ระบบ Navisworks', '',
    '## แหล่งข้อมูล', '', '| Scope | NWC | SHA-256 | Nodes ทุกระดับ | Property keys (display/internal pairs) | Document units |', '|---|---|---|---:|---:|---|']
summary={'source':'direct-nwc-net-api-all-nodes','generatedDate':'2026-10-03','models':{},'spatial':{}}
inventories={}
for scope,path in MODELS.items():
    d=json.loads((OUT/(scope+'.json')).read_text(encoding='utf-8'))
    assert Path(d['ModelFile']).name==path.name
    assert d['TotalNodes']>0
    inventories[scope]=d
    source=dict(file=str(path),sha256=sha(path),totalNodes=d['TotalNodes'],keyPairs=len(d['Keys']),units=d['Units'])
    summary['models'][scope]=source
    lines.append('| '+' | '.join(map(cell,[scope,path,source['sha256'],source['totalNodes'],source['keyPairs'],source['units']]))+' |')
lines+=['','## Properties ที่พบจริง','','จำนวนในตารางเป็น node/property occurrences ไม่ใช่จำนวน physical elements ห้ามรวม Family กับ Type เป็นจำนวนชิ้นงาน เพราะอาจเป็นหลักฐานของชิ้นเดียวกันและ Type เดิมอาจปรากฏซ้ำต่างชั้น','','| Scope | Property | ค่า | จำนวน node ที่มีค่านี้ |','|---|---|---|---:|']
for scope,d in inventories.items():
    for key in d['Keys']:
        if not key['Candidate']:continue
        assert sum(v['Count'] for v in key['Values'])==key['NodeOccurrences']
        for value in key['Values']:
            lines.append('| '+' | '.join(map(cell,[scope,key['DisplayKey'],value['Value'] or '(ว่าง)',value['Count']]))+' |')
lines+=['','## ข้อสรุป','','- OmniClass: พบ property Number/Title ที่ Family และ Type ในทั้งสอง NWC จริง',
    '- Structure Assembly Code: พบ B10 (Superstructure) และ A1020110 (Piles - CIP) ที่ Type; นี่คือ native property ต่างจาก uniformatCode ที่ exporter สร้าง',
    '- ไม่พบ key ชื่อ MasterFormat, OmniFormat หรือ UNIFORMAT เมื่อค้นทั้ง display/internal property names ทุก node ของทั้งสอง NWC',
    '- Structure พบ Type.Keynote = 03310/05100; ยังไม่รับรองว่าเป็น MasterFormat หรือ edition ใด ต้องตรวจ keynote/specification ต้นทางก่อน',
    '- Assembly Code อาจเป็นสัญญาณของการจัดหมวด assembly แต่ยังไม่รับรอง crosswalk/edition จากรูปแบบรหัสเพียงอย่างเดียว',
    '- มีตัวอย่าง AR: Family/Type Lift3 ใต้ Category Doors แต่ OmniClass = 23.75.00.00 / Climate Control (HVAC) ต้องทบทวนกับผู้ทำโมเดลก่อนใช้เป็น authoritative classification',
    '- อย่านำ native Assembly Code สำหรับ piles A1020110 ไปแทน derived A1010 โดยอัตโนมัติ; เป็นคนละแหล่งหลักฐาน ต้องพิจารณา crosswalk แยก',
    '- JSON CASE2 เดิมไม่พบ fields นี้ เพราะ exporter ไม่ส่ง node Type/Family; เพื่อใช้งานต่อควรอ่านข้อมูลจาก ancestor มาผูกกับ instance พร้อม source path โดยไม่เพิ่ม group nodes เข้า BOQ',
    '- รอบนี้ยังไม่ implement inheritance หรือเปลี่ยน CLASSIFY/EIT/pricing/MasterFormat mapping',
    '', '## หลักฐานตัวอย่าง (native property)', '']
for scope,d in inventories.items():
    for key in d['Keys']:
        if key['DisplayKey'] not in ('Type.OmniClass Number','Type.Assembly Code','Type.Keynote'):continue
        for value in key['Values']:
            e=value['Examples'][0]
            lines+=['- '+scope+' / `'+key['DisplayKey']+'` = `'+value['Value']+'`',
                '  - internal key: `'+key['InternalKey']+'`',
                '  - tree: `'+e['AncestorPath']+'`']
lines+=['','## Spatial export ที่กลับมาทำสำเร็จหลังแก้สิทธิ์','','| Scope | Snapshot | Exported nodes | instance id + Category | มี BoundingBox | หน่วยพิกัด |','|---|---|---:|---:|---:|---|']
for scope,name in [('ST','CASE2_ST_ALL'),('AR','CASE2_AR')]:
    path=ROOT/'data/export'/(name+'.spatial.json')
    data=json.loads(path.read_text(encoding='utf-8'))
    entries=[e for e in data['elements'] if e.get('id') and (e.get('properties') or {}).get('Element.Category')]
    with_box=[e for e in entries if e.get('boundingBox') is not None]
    for e in with_box:
        b=e['boundingBox']
        assert all(math.isfinite(b[k]) for k in ('minX','minY','minZ','maxX','maxY','maxZ'))
        assert all(b['min'+axis]<=b['max'+axis] for axis in 'XYZ')
        assert e['coordinateUnits']==data['coordinateUnits']
        for axis in 'XYZ':
            assert math.isclose(e['position'][axis.lower()],b['min'+axis]/2+b['max'+axis]/2,rel_tol=1e-9,abs_tol=1e-9)
    assert len(entries)==len(with_box)
    item=dict(file=str(path),sha256=sha(path),exportedNodes=len(data['elements']),instanceNodes=len(entries),withBoundingBox=len(with_box),units=data['coordinateUnits'])
    summary['spatial'][scope]=item
    lines.append('| '+' | '.join(map(cell,[scope,path.name,item['exportedNodes'],item['instanceNodes'],item['withBoundingBox'],item['units']]))+' |')
lines+=['','BoundingBox/position อยู่ใน navisworks-document coordinates; จุด position เป็น bbox center ไม่ใช่ insertion point. ยังไม่ได้ยืนยัน shared origin/transforms/alignment ของ ST กับ AR จึงยังห้ามใช้ overlap เพื่อตัดปริมาณซ้ำอัตโนมัติ',
    '', 'Document.Units=Feet เป็นหน่วยพิกัดจาก API ไม่ใช่หลักฐานว่า display parameter ทุกชนิดมีหน่วยเดียวกันหรือพร้อมแปลง weight แล้ว',
    '', 'Snapshot .boq.json เดิมไม่ถูกทับหรือเปลี่ยน hashes; .spatial.json เป็นชุด export ใหม่ และไม่ได้เปลี่ยนแหล่งข้อมูลของเซิร์ฟเวอร์ที่กำลังเปิดโดยอัตโนมัติ',
    '', '## ไฟล์ประกอบ','','- ST.json / AR.json: inventory ทุก property key พร้อม counts และ classification candidate values/examples',
    '- summary.json: source hashes, scan counts และ spatial validation totals',
    '- ST.log / AR.log: Navisworks invocation logs',
    '- tools/NwcPropertyInventoryPlugin.cs: reader ที่ไม่กรอง Type/Family',
    '- tools/summarize_nwc_inventory.py: สร้างรายงานและตรวจ finite bbox/min-max/center/source units', '']
(OUT/'REPORT_TH.md').write_text('\n'.join(lines),encoding='utf-8')
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'docs/NWC_CLASSIFICATION_INSPECTION_STATUS_TH.md').write_text('# ตรวจ NWC สำเร็จแล้ว — 3 ตุลาคม 2026\n\nหลังผู้ใช้เปิด/เข้าสู่ระบบ Navisworks อ่านทั้ง ST/AR ด้วย exit code 0 แล้ว พบ OmniClass บน Family/Type และพบ native Assembly Code/Keynote ใน Structure\n\nรายงานฉบับเต็ม: [nwc_property_inventory/REPORT_TH.md](nwc_property_inventory/REPORT_TH.md)\n\nปัญหา NOT Authorized/login requires GUI mode ที่เคยค้างได้รับการแก้แล้ว และ spatial export จริงทำสำเร็จทั้งสองโมเดล\n',encoding='utf-8')
p=ROOT/'docs/SPATIAL_EXPORT_STATUS_TH.md'
p.write_text(p.read_text(encoding='utf-8')+'\n\n## อัปเดตหลังเข้าสู่ระบบ — 3 ตุลาคม 2026\n\nNoGui ใช้งานได้แล้ว ตรวจ inventory จาก NWC สำเร็จ และ export spatial snapshots สำเร็จทั้ง ST/AR: ST BoundingBox ครบ 4,794/4,794 instance nodes; AR ครบ 24,515/24,515 instance nodes หน่วยพิกัด Feet ผล finite/min-max/center validation ผ่าน รายละเอียดใน `nwc_property_inventory/REPORT_TH.md`\n\nยังไม่ยืนยัน alignment ระหว่างโมเดลและยังไม่ทำ auto-deduplication\n',encoding='utf-8')
p=ROOT/'PROJECT_STATUS_HANDOFF_TH.md'
p.write_text(p.read_text(encoding='utf-8')+'\n\n## อัปเดต NWC inspection สำเร็จ — 3 ตุลาคม 2026\n\nหลังเข้าสู่ระบบ Navisworks อ่าน property tree ทุกระดับจาก NWC จริงได้แล้ว พบ native OmniClass บน Family/Type ของ ST/AR และ Assembly Code/Keynote บน Type ของ ST มีตัวอย่าง OmniClass ที่ต้อง review (AR Lift3/Doors แต่ Title=Climate Control HVAC) ยังไม่ได้เพิ่ม inheritance หรือใช้รหัส native แทน CLASSIFY เดิม\n\nspatial export ใหม่สำเร็จ ST bbox ครบ 4,794 instance nodes และ AR 24,515 instance nodes หน่วยพิกัด Feet ตรวจ finite/min-max/center ผ่าน ยังต้องตรวจ shared origin/transforms ก่อน dedup ข้ามโมเดล รายงานเต็ม `docs/nwc_property_inventory/REPORT_TH.md`\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))