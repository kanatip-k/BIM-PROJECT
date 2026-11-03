"""Import reviewed project knowledge atomically; never called by an MCP tool."""
import argparse
import json
from pathlib import Path
from core import build_dataset, GraphStore

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    dataset=build_dataset()
    if not args.dry_run:
        db=GraphStore()
        try:
            db.import_dataset(dataset)
        finally:
            db.close()
    report={'version':dataset['version'],'nodes':len(dataset['nodes']),'relationships':len(dataset['edges']),'source_hashes':dataset['hashes'],'imported':not args.dry_run}
    Path(__file__).with_name('import_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
