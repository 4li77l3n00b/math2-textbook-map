"""Invoke the configured PaddleOCR-VL MCP server over its stdio transport.

Credentials are read from project configuration and never embedded in outputs.
Each result is checkpointed so completed documents are not submitted again.
"""
import argparse
import asyncio
import base64
import json
import os
from pathlib import Path
import tomllib

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest')
    parser.add_argument('--sample')
    parser.add_argument('--list-tools', action='store_true')
    args = parser.parse_args()
    cfg = tomllib.loads((ROOT/'.codex/config.toml').read_text())['mcp_servers']['PaddleOCR-VL-1.6']
    env = dict(os.environ)
    env.update(cfg['env'])
    params = StdioServerParameters(command=cfg['command'], args=cfg['args'], env=env)
    raw = ROOT/'output/ocr/raw'
    raw.mkdir(parents=True, exist_ok=True)
    with (ROOT/'tmp/pdfs/mcp-server.log').open('a') as log:
        async with stdio_client(params, errlog=log) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=1200) as session:
                info = await session.initialize()
                print('MCP initialized:', info.server_info.name, flush=True)
                ts = await session.list_tools()
                (ROOT/'output/ocr/mcp-tools.json').write_text(ts.model_dump_json(indent=2))
                if args.list_tools:
                    print(ts.model_dump_json(indent=2), flush=True)
                    return
                docs = json.loads(Path(args.manifest).read_text()) if args.manifest else [{'id':'sample','path':args.sample}]
                for i, doc in enumerate(docs):
                    out = raw/(doc['id']+'.json')
                    if out.exists() and not json.loads(out.read_text()).get('is_error'):
                        print('SKIP',doc['id'],flush=True)
                        continue
                    print(f"OCR {i+1}/{len(docs)} {doc['id']}",flush=True)
                    result = await session.call_tool('paddleocr_vl', {
                        'input_data':str((ROOT/doc['path']).resolve()),
                        'output_mode':'detailed', 'return_images':True,
                    })
                    out.write_text(result.model_dump_json(indent=2))
                    if result.is_error:
                        print('ERROR',doc['id'], ' '.join(c.text for c in result.content if c.type=='text'),flush=True)
                        break
                    folder=ROOT/'output/ocr'/doc['id']
                    folder.mkdir(exist_ok=True)
                    text=[]
                    for j, content in enumerate(result.content):
                        if content.type=='text': text.append(content.text)
                        elif content.type=='image':
                            ext='png' if content.mime_type=='image/png' else 'jpg'
                            name=f'image-{j:03}.{ext}'
                            (folder/name).write_bytes(base64.b64decode(content.data))
                            text.append(f'\n![原文插图]({name})\n')
                    (folder/'raw.md').write_text('\n'.join(text))
                    print('DONE',doc['id'], 'characters',sum(len(t) for t in text), flush=True)

if __name__=='__main__':
    asyncio.run(main())
