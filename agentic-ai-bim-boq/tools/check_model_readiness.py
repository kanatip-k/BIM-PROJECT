"""Inspect six CASE2 NWC evidence snapshots without changing BOQ rules."""
import json, hashlib, math, re, sys
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/model_readiness_20261003'
sys.path.insert(0,str(ROOT/'python_app'))
from boq_workflow.pipeline import run_pipeline, MEASURE_KEYS
from boq_workflow.configuration import load_bundle
from boq_workflow.service import _pipeline_input
FILES={
'AR':Path(r'D:\BIM-PROJECT\Case Study\Case2\01_ARCHITECTURE\02_NWC\CASE2_AR.nwc'),
'ST':Path(r'D:\BIM-PROJECT\Case Study\Case2\04_STRUCTURE\02_NWC\CASE2_ST_ALL.nwc'),
**{s:Path(r'D:\BIM-PROJECT\Case Study\Case2\05_MEP\02_NWC')/('CASE2_'+s+'.nwc') for s in ('EE','FP','ME','SN')}}
EXPECTED={'AR':'84B9527653FD632410D2EEEB2F45603C547AEB4CCC259B2D01FC1C1C0A5363C3','ST':'9998F4EEB4F2B2B00543DCB5B6076EBA89B05A09BA943DABC0E167FA9ED0B0A3','EE':'7B800BCD9CEF5E88395FD652FCD7F4DAAF9CF19FD84E1895562DB5A3E2112659','FP':'B0D29D6BEDED9CE672E3583FD396CAE0DED90D2C062B132D26D5069D7B79E53C','ME':'968C5472838406AD0612A3DF6D1E6E98A9FD6B5D7B9B5E4EC941AA41EA3A3C0D','SN':'764BE2E61C4D1B0FCEA195A92FB84335093C212394B6A91B0CCFAFEC968A0CEF'}
def sha(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest().upper()
def positive(v):
    text=str(v).strip()
    if ':' in text:text=text.split(':',1)[1].strip()
    try:n=float(text);return math.isfinite(n) and n>0
    except (ValueError,TypeError):return False
def cell(v):return str(v).replace('|','\\|').replace('\n',' ')
def main():
    records=[]
    bundle=load_bundle()
    for scope,source in FILES.items():
        assert sha(source)==EXPECTED[scope], 'Source changed during inspection: '+str(source)
        if scope in ('AR','ST'):
            inv_path=ROOT/'docs/nwc_property_inventory'/(scope+'.json')
            snapshot_path=ROOT/'data/export'/('CASE2_'+('ST_ALL' if scope=='ST' else scope)+'.classified-source.json')
            reused=True
        else:
            inv_path=OUT/(scope+'.inventory.json');snapshot_path=OUT/(scope+'.snapshot.json');reused=False
        inv=json.loads(inv_path.read_text(encoding='utf-8-sig'))
        snap=json.loads(snapshot_path.read_text(encoding='utf-8-sig'))
        entries=[e for e in snap['elements'] if e.get('id') and e['properties'].get('Element.Category')]
        measure={}
        for kind,keys in MEASURE_KEYS.items():
            measure[kind]={'keys':list(keys),'presentNonempty':sum(any(str(e['properties'].get(k,'')).strip() for k in keys) for e in entries),'positiveNumeric':sum(any(positive(e['properties'].get(k,'')) for k in keys) for e in entries)}
        native=Counter((r['propertyKey'],r['value']) for e in entries for r in e['classificationEvidence']['nativeProperties'])
        keynames={k['DisplayKey'] for k in inv['Keys']}
        qto=[k for k in sorted(keynames) if 'qto' in k.casefold()]
        predef=[k for k in sorted(keynames) if 'predefinedtype' in re.sub('[^a-z]','',k.lower())]
        numbertitle=[]
        for e in entries:
            rows=e['classificationEvidence']['nativeProperties']
            nums={r['value'] for r in rows if 'omniclass' in r['kind'] and r['propertyKey'].endswith(('Number','Code'))}
            titles={r['value'] for r in rows if 'omniclass' in r['kind'] and r['propertyKey'].endswith(('Title','Description'))}
            if nums or titles:numbertitle.append((e['properties']['Element.Category'],tuple(sorted(nums)),tuple(sorted(titles))))
        omni_pairs=Counter(numbertitle)
        rec={'scope':scope,'sourceFile':str(source),'sourceSha256':EXPECTED[scope],'bytes':source.stat().st_size,'reusedHashIdenticalPriorInspection':reused,'inventoryFile':str(inv_path),'snapshotFile':str(snapshot_path),'snapshotSha256':sha(snapshot_path),'allNwcNodes':inv['TotalNodes'],'propertyKeyPairs':len(inv['Keys']),'exportNodes':len(snap['elements']),'idCategoryElements':len(entries),'duplicateIds':len(entries)-len({e['id'] for e in entries}),'bboxAvailable':sum(e.get('boundingBox') is not None for e in entries),'coordinateUnits':snap['coordinateUnits'],'centerlineCategoryCount':sum(e['properties']['Element.Category'].casefold().replace(' ','')=='centerline' for e in entries),'categories':dict(Counter(e['properties']['Element.Category'] for e in entries).most_common()),'measuresUsingCurrentAliases':measure,'nativeEvidenceElements':sum(bool(e['classificationEvidence']['nativeProperties']) for e in entries),'omniElements':len(numbertitle),'nativeMasterFormatElements':sum(any(r['kind']=='masterformat' for r in e['classificationEvidence']['nativeProperties']) for e in entries),'nativeUniformatElements':sum(any(r['kind']=='uniformat' for r in e['classificationEvidence']['nativeProperties']) for e in entries),'keynoteElements':sum(any(r['kind']=='keynote' for r in e['classificationEvidence']['nativeProperties']) for e in entries),'nativePropertyValues':[{'key':k,'value':v,'elementOccurrences':n} for (k,v),n in sorted(native.items())],'omniCategoryPairs':[{'category':c,'numbers':list(n),'titles':list(t),'elementCount':count} for (c,n,t),count in sorted(omni_pairs.items())],'qtoKeysAllNodes':qto,'predefinedTypeKeysAllNodes':predef}
        badbox=0
        for e in entries:
            b=e.get('boundingBox')
            if not b:continue
            if not all(math.isfinite(b[k]) for k in ('minX','minY','minZ','maxX','maxY','maxZ')) or any(b['min'+a]>b['max'+a] for a in 'XYZ'):badbox+=1
        rec['invalidBboxCount']=badbox
        result=run_pipeline(snap['modelName'],[_pipeline_input(e) for e in snap['elements']],bundle)
        classified=result['classifiedElements'];measured=result['elements']
        rec['currentPipelineDiagnostic']={'acquired':result['stages'][0]['outputCount'],'classified':len(classified),'resolvedElementCodes':dict(Counter(e['element_code'] for e in classified if e.get('element_code'))),'resolved':sum(bool(e.get('element_code')) for e in classified),'classifiedDisciplines':dict(Counter(e['discipline'] for e in classified)),'quantityNonNull':sum(e.get('quantity') is not None for e in measured),'boqLines':len(result['boq']['lines']),'issues':{r['code']:sum(int(x.get('count',1)) for x in result['issues'] if x['code']==r['code']) for r in result['issues']},'centerlineClassified':sum(e['properties'].get('Element.Category','').casefold().replace(' ','')=='centerline' for e in classified),'centerlineCodes':dict(Counter(e.get('element_code') or 'UNRESOLVED' for e in classified if e['properties'].get('Element.Category','').casefold().replace(' ','')=='centerline')),'quantityOutputsAreNotValidatedUnitConversions':True}
        records.append(rec)
        print(scope,rec['idCategoryElements'],'elements, native',rec['nativeEvidenceElements'],'MF',rec['nativeMasterFormatElements'],'resolved',rec['currentPipelineDiagnostic']['resolved'],flush=True)
        del result,classified,measured,entries,snap,inv
    (OUT/'SUMMARY.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# ตรวจความพร้อมของ CASE2 NWC ทั้ง 6 ไฟล์','','วันที่: 3 ตุลาคม 2026','','ST/AR ที่ผู้ใช้ส่งมาตรง SHA-256 กับโมเดลที่เปิดตรวจจริงในรอบก่อน จึงใช้ inventory/export เดิมที่ยืนยันแล้ว; MEP EE/FP/ME/SN เปิดอ่านใหม่ผ่าน Navisworks API ทั้ง inventory ทุก node และ snapshot ของ exporter. เก็บ MEP export ในโฟลเดอร์ audit นี้ ไม่ใส่ data/export ไม่เปลี่ยน source ของเว็บและไม่แก้ CLASSIFY/pricing.','','## ข้อมูลที่อ่านได้','','| File | NWC nodes ทุกระดับ | Export nodes | มี id+Category | มี bbox | Native classification | Native MasterFormat | Native UNIFORMAT | Keynote |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in records:lines.append('| '+' | '.join(map(cell,[r['scope'],r['allNwcNodes'],r['exportNodes'],r['idCategoryElements'],r['bboxAvailable'],r['nativeEvidenceElements'],r['nativeMasterFormatElements'],r['nativeUniformatElements'],r['keynoteElements']]))+' |')
    lines+=['','จำนวน id+Category ยังรวม Center line หากมี ไม่ใช่จำนวนชิ้นงาน BOQ ที่อนุมัติแล้ว. Native classification รวม System Classification และอื่นๆ ด้วย ไม่เท่ากับมี OmniClass/MasterFormat ทุกตัว. bbox/position เป็น Document coordinates; ไม่ยืนยัน shared origin ข้ามโมเดล.','','## ปริมาณที่พบโดยใช้ property aliases ปัจจุบัน','','| File | Length > 0 | Area > 0 | Volume > 0 | Center line category | Units พิกัด |','|---|---:|---:|---:|---:|---|']
    for r in records:lines.append('| '+' | '.join(map(cell,[r['scope'],r['measuresUsingCurrentAliases']['LENGTH']['positiveNumeric'],r['measuresUsingCurrentAliases']['AREA']['positiveNumeric'],r['measuresUsingCurrentAliases']['VOLUME']['positiveNumeric'],r['centerlineCategoryCount'],r['coordinateUnits']]))+' |')
    lines+=['','เป็นจำนวน element ที่มีค่าบวกใน aliases ปัจจุบัน ไม่ใช่ผลรวมปริมาณ. Native DoubleLength/DoubleArea/DoubleVolume ยังต้องยืนยัน unit conversion และ quantity basis. ค่า 0 ในตารางนี้ไม่ได้พิสูจน์ว่า NWC ไม่มี parameter ปริมาณชื่ออื่น. ดูรายการ key ทุกตัวใน *.inventory.json.','','## Pipeline ปัจจุบัน (diagnostic เท่านั้น)','','| File | Acquired | Classified | Resolved element_code | Quantity ไม่ null | BOQ lines | Center line เข้า CLASSIFY |','|---|---:|---:|---:|---:|---:|---:|']
    for r in records:
        p=r['currentPipelineDiagnostic'];lines.append('| '+' | '.join(map(cell,[r['scope'],p['acquired'],p['classified'],p['resolved'],p['quantityNonNull'],p['boqLines'],p['centerlineClassified']]))+' |')
    lines+=['','การได้ quantity/BOQ line ไม่ใช่การรับรองความถูกต้องของหน่วย กฎวัด EIT หรือราคา. ผลนี้ใช้วัดช่องว่างของโค้ดเดิม ไม่เพิ่ม keyword หรือแก้ mapping เพื่อให้ตัวเลขดีขึ้น.','','## รายละเอียดแต่ละไฟล์']
    for r in records:
        lines+=['', '### '+r['scope'], '', '- Source: `'+r['sourceFile']+'`','- SHA-256: `'+r['sourceSha256']+'`','- Duplicate IDs: '+str(r['duplicateIds'])+'; Invalid bbox: '+str(r['invalidBboxCount']),'- Qto keys: '+(', '.join(r['qtoKeysAllNodes']) or 'ไม่พบ'),'- PredefinedType keys: '+(', '.join(r['predefinedTypeKeysAllNodes']) or 'ไม่พบ'),'','| Category | จำนวน id+Category elements |','|---|---:|']
        for k,n in r['categories'].items():lines.append('| '+cell(k)+' | '+str(n)+' |')
        lines+=['','| Native property | Raw value | Element occurrences |','|---|---|---:|']
        for v in r['nativePropertyValues']:lines.append('| '+cell(v['key'])+' | '+cell(v['value'])+' | '+str(v['elementOccurrences'])+' |')
        lines+=['','Resolved codes: `'+json.dumps(r['currentPipelineDiagnostic']['resolvedElementCodes'],ensure_ascii=False)+'`','', 'Classified disciplines: `'+json.dumps(r['currentPipelineDiagnostic']['classifiedDisciplines'],ensure_ascii=False)+'`','', 'Center line codes: `'+json.dumps(r['currentPipelineDiagnostic']['centerlineCodes'],ensure_ascii=False)+'`']
    lines+=['','## สิ่งที่ต้องยืนยันก่อนใช้โมเดลใหม่','','- Shared coordinates/transforms ของทุก discipline เพื่อเทียบตำแหน่งและตรวจชิ้นงานซ้ำ; การมี bbox ไม่ได้ยืนยัน alignment','- ต้องแยก Center line / geometry representation / physical instance ก่อนรวมปริมาณ MEP และตรวจ cross-model duplicates ด้วย ไม่ใช้เพียงชื่อหรือ cost code ตัดซ้ำ','- ยืนยันหน่วยของ native quantities และ unit conversion ก่อนเชื่อผลราคา','- Native MasterFormat/UNIFORMAT/OmniClass ที่พบเป็นหลักฐานจากโมเดล ไม่ควรใช้แทน crosswalk ที่ผ่านการตรวจแล้วโดยอัตโนมัติ','- ตรวจ Category–OmniClass ใน MEP แยกจาก audit ST/AR เพราะ MEP มี OmniClass Code/Description อีกชุดต่างจาก Number/Title และมี System Classification','- ผนัง Structure ยังรอ glossary; Architecture Floors 10 Type ยังรอคำตอบผู้ใช้; ไม่ map S008 หรือ A008–A011 เพิ่มในรอบนี้','- ทดสอบโมเดลใหม่ด้วย inventory+source hashes ก่อนปรับ rules และเปรียบเทียบ regression snapshot เดิมแยกจาก dataset ใหม่']
    (OUT/'REPORT_TH.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
if __name__=='__main__':main()
