"""Reproducible Claude-style stdio client; saves actual tool responses."""
import asyncio
import json
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    root=Path(__file__).resolve().parent
    async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(root/'server.py')])) as (read,write):
        async with ClientSession(read,write) as session:
            init=await session.initialize()
            tools=await session.list_tools()
            results={'initialize':init.model_dump(by_alias=True),'tools':tools.model_dump(by_alias=True),'calls':[]}
            for name,args in [
                ('ontology_health',{}),
                ('resolve_crosswalk',{'element_code':'S031'}),
                ('resolve_crosswalk',{'element_code':'S001'}),
                ('search_ontology',{'query':'ฐานราก','kind':'WorkItem','limit':5}),
                ('get_concept',{'concept_id':'boq:S001'}),
                ('get_measurement_requirements',{'element_code':'S028'}),
                ('classify_element',{'scope':'Structure','element':{'id':'SMOKE-STEEL','uniformatCode':'B1011','boqEligible':True,
                    'properties':{'Element.Category':'Structural Columns','Element Properties.StructuralMaterialType':'Steel'}}}),
                ('classify_elements',{'scope':'Architecture','elements':[{'id':'SMOKE-FLOOR','uniformatCode':'B1010','boqEligible':True,
                    'properties':{'Element.Category':'Floors','Element.Type':'F11-50mm'}},{'id':''}]})]:
                response=await session.call_tool(name,args)
                record=response.model_dump(by_alias=True)
                if record['isError']:
                    raise RuntimeError(str(record))
                results['calls'].append({'tool':name,'arguments':args,'response':record})
    path=root/'mcp_smoke_evidence.json'
    path.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'MCP initialized; {len(tools.tools)} tools listed; {len(results["calls"])} calls succeeded. Evidence: {path}')

if __name__=='__main__':
    asyncio.run(main())
