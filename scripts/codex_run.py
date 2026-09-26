"""Run one `codex exec` job with a JSON-schema answer, keeping usage and the commands the agent ran."""
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'gpt-6-astra'


def run_codex(prompt, schema_path, out_path, cwd=ROOT, images=(), env=None, config=(), timeout=3600):
    """Returns {'ok', 'result', 'usage', 'commands', 'seconds', 'error'}; the event log goes next to out_path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    last = out_path.with_suffix('.last.json')
    cmd = ['codex', 'exec', '-m', MODEL, '-s', 'read-only', '--ephemeral', '--skip-git-repo-check',
           '-C', str(cwd), '--json', '--output-schema', str(schema_path), '-o', str(last)]
    for c in config:
        cmd += ['-c', c]
    for im in images:
        cmd += ['-i', str(im)]
    cmd += ['--', prompt]  # `-i` takes several values: the separator keeps the prompt out of it
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                       env={**os.environ, **(env or {})})
    seconds = round(time.time() - t0, 1)
    usage, commands = {}, []
    for line in p.stdout.splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get('type') == 'turn.completed':
            for k, v in e.get('usage', {}).items():
                usage[k] = usage.get(k, 0) + v
        item = e.get('item', {})
        if e.get('type') == 'item.completed' and item.get('type') == 'command_execution':
            commands.append({'command': item['command'], 'exit_code': item.get('exit_code'),
                             'output_chars': len(item.get('aggregated_output') or '')})
    out_path.with_suffix('.events.jsonl').write_text(p.stdout, encoding='utf-8')
    res = {'ok': False, 'result': None, 'usage': usage, 'commands': commands, 'seconds': seconds,
           'finished': datetime.now(timezone.utc).isoformat(), 'error': None}
    if p.returncode or not last.exists():
        res['error'] = f'rc={p.returncode}: {p.stderr[-2000:]}'
        return res
    try:
        res['result'] = json.loads(last.read_text(encoding='utf-8'))
        res['ok'] = True
        last.unlink()
    except json.JSONDecodeError as e:
        res['error'] = f'bad json: {e}'
    return res
