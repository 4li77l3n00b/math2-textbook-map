"""Same mapping task as map_questions.py, but calling gpt-6-astra directly on the relay's Responses API.

Why: through `codex exec` every turn re-sends ~16k tokens of codex's own instructions/tool schemas, and the relay
never caches across codex sessions. Here the only tool is the textbook lookup (textbook_cli.py run in a subprocess), the
shared instructions + both tables of contents form a fixed prefix sent with a constant prompt_cache_key (cached
across questions), and the model may issue several lookups per turn.

  python3 scripts/map_direct.py run [GS|LA] [QUESTION_ID ...] [--out DIR]   (default out: output/mapping/raw)
Results use the same JSON layout as map_questions.py, so `map_questions.py post` works unchanged.

Long runs: the relay goes to sleep periodically. Any 5xx/429/network error pauses *all* workers; one of them
probes the API every PROBE_EVERY seconds with a ~10-token request, and when it answers every worker retries the
very turn it was on (conversations are not thrown away). Finished questions are files, so a run can also be killed
and restarted at any time; `run` repeats passes until nothing is left or a pass makes no progress.
Stop gracefully: `touch output/mapping/STOP` (in-flight questions finish, no new ones start).
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
import shlex
import subprocess
import faulthandler
import signal
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_textbook_index import save, jsonsave  # noqa: E402
import map_questions as mq  # noqa: E402

def _api_url():
    """Responses endpoint of the relay: $MATH2_API_URL, else base_url in ~/.codex/config.toml + /responses."""
    if os.environ.get('MATH2_API_URL'):
        return os.environ['MATH2_API_URL']
    import re
    cfg = Path('~/.codex/config.toml').expanduser().read_text()
    return re.search(r'base_url\s*=\s*"([^"]+)"', cfg).group(1).rstrip('/') + '/responses'


URL = _api_url()
MODEL = 'gpt-6-astra'
EFFORT = 'medium'        # user decision 2026-09-24 (was high, as in the codex config)
CACHE_KEY = 'math2-textbook-mapping-v4'  # v4: linear algebra = 王宽程 (LA) first, LALU as supplement
WORKERS = 4
MAX_TURNS = 24
PROBE_EVERY = 300        # seconds between availability probes while the relay sleeps
MAX_OUTAGE = 48 * 3600   # give up after this long
STALL_LIMIT = 300        # abort a stream with no real event for this long (the relay keeps idle streams
                         # alive with SSE comment pings, so the socket timeout alone never fires)
REQUEST_LIMIT = 1200     # abort any single request running longer than this
BUSY_LIMIT = 20          # consecutive 'conversation is busy' retries (15 s apart) before treating as outage
QUESTION_LIMIT = 2400    # give up on one question after this long (outage pauses excluded); retried next pass
WATCHDOG_IDLE = 900      # no question finished for this long while the API is up -> dump worker states + stacks
MAX_TOOL_CHARS = 6000   # tool output is the main uncached cost: keep each lookup small
ALLOWED = {'read', 'blocks', 'search', 'cards', 'card'}

TOOL = {
    'type': 'function', 'name': 'textbook', 'strict': True,
    'description': ('只读查询教材。args 是一条子命令及其参数，例如 "read GS1/3/3.1/3.1.1 --limit 30"、'
                    '"blocks GS1-p144-b23 GS1-p144-b27"、"search 拉格朗日中值定理 --book GS1"、'
                    '"cards LA/4/4.3/4.3.3 --brief"、"card LA/4/4.3/4.3.3#diag_criterion"。'
                    '可以在一次回复中并行发起多个调用。'),
    'parameters': {'type': 'object', 'additionalProperties': False, 'required': ['args'],
                   'properties': {'args': {'type': 'string'}}},
}

STATIC = '''你是一名做完考研数学二真题的学生，现在要“翻教材”：(一) 把一道题解答中用到的每一条知识依据落实到教材原文；(二) 判断这道题在教材知识体系里考查的是哪一部分。每次对话给你一道题（题干、参考答案、参考解析），你用 textbook 工具查书，最后按 JSON 格式作答。

## 教材
- 高等数学题用 GS1 = 高等数学上册、GS2 = 高等数学下册。块形如 `GS1-p144-b23 文本`，是 OCR 文本，可能有少量识别错误。
- 线性代数题**先用 LA = 王宽程《线性代数》**（主教材，块形如 `LA-p070-b12 文本`，OCR 文本）。只有 LA 中没有该结论的一般性陈述时（如秩的不等式、伴随矩阵的秩与行列式、代数重数与几何重数、范德蒙德行列式等），才用 LALU = 线性代数讲义《线性代数：未竟之美》补充，并在 why 中写明“王宽程未见”。LALU 的块形如 `LALU-c14-b0050 [theorem 定理14.3] 文本`，文本是 LaTeX 源码，类型中带书中编号；讲义以线性空间、线性映射的抽象语言叙述，书中只有抽象版本时引用抽象版本，并在 why 中说明对应关系。knowledge 请写出书中编号（如“定理 2.2”“定理14.3”）。

## textbook 工具的子命令
- `read NODE_ID [--from UID] [--limit N] [--width W]`：按阅读顺序读某节正文块（建议 --limit 30 --width 400 先浏览定位，再用 blocks 读全文）
- `blocks UID [UID_END] [--context K]`：读指定块或区间的全文
- `search 关键词 [--book GS1|GS2|LA|LALU]`：全文检索（空格分隔的多个词表示同时包含）
- `cards NODE_ID --brief`：列出某节的知识卡片（按书整理的知识点：编号、名称）；`card CARD_ID`：查看一张卡片的概要及原文
查找要高效：可在一次回复中并行发起多个查询；通常 4–8 轮内完成。

## 第一部分：解题依据 → 教材原文
1. 把参考解析拆成若干步骤（steps），每步写清用了什么数学依据；解析省略的隐含依据也要补出（如“闭区间连续函数可取到最值”）。
2. 像人翻书一样：根据目录定位章节，用 read 或 search 找到具体段落，读原文确认后再引用。解题用到其他章节的工具时（如求极限用泰勒公式）要去对应章节找。参考解析常把书中讲过的标准方法或题型写得很简略（如“写成 (xy)′=x 再积分”其实是一阶线性微分方程的“凑导数法”），要识别出来并引用书中该方法或概念本身，而不只是引用计算中用到的零散公式。
3. 每条依据一个引用：start_uid..end_uid 是直接陈述该依据的**连续**块区间，尽量小（通常 1–5 块，即定理/定义/公式本身）；优先引用定义、定理、公式、书中明确讲的方法，只有书中没有一般性陈述时才引用例题。quote 从区间内原文**逐字**摘一句（10–80 字，照抄工具显示的原文，含其中的 LaTeX）。knowledge 用书中的叫法；role：core / auxiliary / prerequisite。
4. 出处选择：同一结论在书中多处出现时（如公式汇总表、推导它的例题、后文或另一册的复述），引用首次正式陈述它的定理、定义、公式或命题，不引复述；只有书中没有一般性陈述、只在例题或注里出现时才引例题或注。优先引用数二范围内的章节（上面目录所列）：参考解析若借用了超纲工具（如用幂级数求 f⁽ⁿ⁾(0)），应另给出范围内的等价依据（如泰勒公式、常见函数的麦克劳林公式）作为主要引用，超纲出处至多作为 auxiliary 补充并在 why 中注明“超纲”。
5. 粒度：只引用大学课程层面的知识。中学层面的代数与初等函数运算（对数/指数运算律、不等式同乘除正数、解代数方程、三角恒等式、配方等）不必引用，也不列入 not_in_textbook，除非它恰是考查重点。同一知识多步使用只引用一次（steps 列出所有步号）。
6. 教材里确实找不到的课程层面依据放入 not_in_textbook，写明查过哪里；不要勉强凑不相干的段落。

## 第二部分：考查主题（与解析路线无关）
7. 暂时忘掉参考解析用的方法，从命题意图看：这道题考的是教材哪部分知识、属于书中哪类题型？例如“证明 f''≥0 与某积分不等式等价”考的是凹凸性，即使参考解析用中值定理和泰勒公式完成；“已知 A 相似于对角阵求参数”考的是可对角化的判定，即使参考解析主要在解线性方程组。用 cards 查看候选小节的卡片（线性代数优先选 LA 的卡片，LA 没有对应卡片时才选 LALU 的），选 1–3 张 primary（最直接的考查对象）和若干 secondary（常用解法或关联知识），card_id 必须是 cards 输出中真实存在的；reason 说明理由。若主题与解析路线不同，在 topic_note 中说明。

## 目录：高等数学（GS1/GS2，数二范围）
{toc_gs}

## 目录：线性代数（LA = 王宽程，主教材；LALU = 讲义，补充）
{toc_la}
'''

USER = '''## 题目 {qid}（{subject}，请查{books}）
{stem}

## 参考答案
{answer}

## 参考解析
{solution}
'''

KEY = json.loads(Path('~/.codex/auth.json').expanduser().read_text())['OPENAI_API_KEY']


def msg(role, text):
    return {'type': 'message', 'role': role, 'content': [{'type': 'input_text', 'text': text}]}


class Outage(Exception):
    """Relay unavailable (5xx, 429, network): wait for it to come back, then retry the same request."""


class Busy(Exception):
    """The relay treats one prompt_cache_key as one conversation and rejects concurrent requests on it."""


class RequestError(Exception):
    """The request itself was rejected (4xx other than 429): retrying will not help."""


def log(*a):
    print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'), *a, flush=True)


def post_once(body):
    data = json.dumps({**body, 'stream': True}).encode()
    req = urllib.request.Request(URL, data=data, headers={
        'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json', 'Accept': 'text/event-stream'})
    items, usage, failed = [], None, None
    t0 = last = time.time()
    try:
        with urllib.request.urlopen(req, timeout=STALL_LIMIT) as resp:
            for raw in resp:
                now = time.time()
                if now - last > STALL_LIMIT or now - t0 > REQUEST_LIMIT:
                    raise Outage(f'stream stalled ({now - last:.0f} s without events, {now - t0:.0f} s total)')
                line = raw.decode('utf-8', 'replace').strip()
                if not line.startswith('data:') or line[5:].strip() == '[DONE]':
                    continue  # keep-alive comments / blank separators
                last = now
                ev = json.loads(line[5:])
                t = ev.get('type')
                if t == 'response.output_item.done':
                    items.append(ev['item'])
                elif t == 'response.completed':
                    usage = ev['response'].get('usage')
                elif t in ('response.failed', 'response.incomplete', 'error'):
                    failed = json.dumps(ev, ensure_ascii=False)[:500]
    except urllib.error.HTTPError as e:
        err = f'HTTP {e.code}: {e.read().decode(errors="replace")[:300]}'
        if 'server_busy' in err or 'conversation is busy' in err:
            raise Busy(err)
        raise (Outage if e.code >= 500 or e.code == 429 else RequestError)(err)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, json.JSONDecodeError) as e:
        raise Outage(f'{type(e).__name__}: {e}')
    if failed:
        raise Outage(failed)  # upstream failed mid-stream: treat like an outage, the same turn is retried
    if usage is None:
        raise Outage('stream ended without response.completed')
    return items, usage


_state = {}              # thread id -> [question, phase, since]; monotonic clock: suspend time not counted
_last_done = [time.monotonic()]


def phase(p, qid=None):
    st = _state.setdefault(threading.get_ident(), [None, None, 0])
    if qid is not None:
        st[0] = qid
    st[1], st[2] = p, time.monotonic()


def dump_states(reason):
    log(f'watchdog: {reason}')
    now = time.monotonic()
    for t, (qid, ph, since) in sorted(_state.items(), key=lambda x: str(x[1][0])):
        log(f'  worker {t}: {qid} {ph} for {now - since:.0f} s')
    faulthandler.dump_traceback(file=sys.stdout, all_threads=True)
    sys.stdout.flush()


def watchdog():
    while True:
        time.sleep(60)
        if _api_up.is_set() and time.monotonic() - _last_done[0] > WATCHDOG_IDLE:
            dump_states(f'no question finished for {(time.monotonic() - _last_done[0]) / 60:.0f} min')
            _last_done[0] = time.monotonic()  # dump again only after another idle period


_prober = threading.Lock()
_api_up = threading.Event()
_api_up.set()


def wait_for_api(reason):
    """First caller probes until the API answers; the other workers just wait for that."""
    if _prober.acquire(blocking=False):
        _api_up.clear()
        log(f'API unavailable, pausing all workers: {reason[:200]}')
        t0 = time.time()
        try:
            while time.time() - t0 < MAX_OUTAGE:
                time.sleep(PROBE_EVERY)
                try:
                    post_once({'model': MODEL, 'input': [msg('user', '只回答 OK')], 'store': False,
                               'reasoning': {'effort': 'low'}})
                    log(f'API back after {(time.time() - t0) / 60:.0f} min, resuming')
                    return
                except (Outage, RequestError) as e:
                    log(f'still unavailable ({(time.time() - t0) / 60:.0f} min): {str(e)[:120]}')
            raise RuntimeError(f'API unavailable for more than {MAX_OUTAGE / 3600:.0f} h')
        finally:
            _api_up.set()
            _prober.release()
    else:
        _api_up.wait()


class QuestionTimeout(Exception):
    pass


def post(body, budget=None):
    """One Responses call that survives relay sleeps; returns (output_items, usage).

    budget: [seconds_left] shared by one question; time spent while the API is paused does not count."""
    quick = busy = 0
    while True:
        phase('waiting-api')
        _api_up.wait()
        if budget is not None and budget[0] <= 0:
            raise QuestionTimeout(f'question exceeded {QUESTION_LIMIT} s')
        t = time.monotonic()
        try:
            phase('request')
            return post_once(body)
        except Busy as e:
            busy += 1
            log(f'busy ({busy}/{BUSY_LIMIT}): {str(e)[:100]}')
            if busy < BUSY_LIMIT:
                phase('busy-sleep')
                time.sleep(15)
                continue
            busy = 0
            wait_for_api(str(e))
            continue
        except Outage as e:
            quick += 1
            log(f'request failed ({quick}): {str(e)[:160]}')
            if quick <= 2:  # brief hiccup: short retries before declaring an outage
                phase('retry-sleep')
                time.sleep(30 * quick)
                continue
            wait_for_api(str(e))
            quick = 0
        finally:
            if budget is not None and _api_up.is_set():
                budget[0] -= time.monotonic() - t


def run_tool(args):
    """Run one textbook_cli subcommand in a subprocess (stdout redirection is not thread-safe)."""
    try:
        argv = shlex.split(args)
    except ValueError as e:
        return f'参数解析失败：{e}'
    if not argv or argv[0] not in ALLOWED:
        return f'不支持的子命令；可用：{", ".join(sorted(ALLOWED))}'
    if argv[0] == 'read':  # browse compactly unless the model asks otherwise
        argv += [x for x, flag in (('--limit', '30'), ('--width', '400')) if x not in argv for x in (x, flag)]
    p = subprocess.run([sys.executable, str(ROOT / 'scripts/textbook_cli.py'), *argv], capture_output=True,
                       text=True, timeout=120)
    out = p.stdout + (p.stderr[-2000:] if p.returncode else '')
    return out if len(out) <= MAX_TOOL_CHARS else out[:MAX_TOOL_CHARS] + '\n…（输出过长已截断，请缩小范围）'


def warm_cache(prefix):
    """One tiny request per worker key with the shared prefix, so first questions hit the cache too."""
    for w in range(WORKERS):
        # same tools and output format as real requests: they are part of the cached prefix
        _, u = post({**request_body(f'{CACHE_KEY}-w{w}'), 'tool_choice': 'none', 'reasoning': {'effort': 'low'},
                     'input': [msg('developer', prefix), msg('user', '准备好了吗？只回答 OK。')]})
        log(f'cache warm-up w{w}: input', u.get('input_tokens'), 'cached',
            (u.get('input_tokens_details') or {}).get('cached_tokens'))


def request_body(key):
    return {'model': MODEL, 'tools': [TOOL], 'tool_choice': 'auto', 'parallel_tool_calls': True,
            'reasoning': {'effort': EFFORT}, 'include': ['reasoning.encrypted_content'], 'store': False,
            'prompt_cache_key': key,
            'text': {'format': {'type': 'json_schema', 'name': 'mapping', 'schema': mq.SCHEMA, 'strict': True}}}


def static_prefix():
    return STATIC.format(toc_gs=mq.toc_text('GS'), toc_la=mq.toc_text('LA'))


_worker_ids = {}
_worker_lock = threading.Lock()


def cache_key():
    """One prompt_cache_key per worker thread: the relay rejects concurrent requests sharing a key, and a key
    used by one sequential worker still carries the shared prefix cache from question to question."""
    t = threading.get_ident()
    with _worker_lock:
        return f'{CACHE_KEY}-w{_worker_ids.setdefault(t, len(_worker_ids)) % WORKERS}'


def map_one(q, prefix, out_dir):
    qid, sub = q['question_id'], q['_subject']
    out = out_dir / f'{qid}.json'
    if out.exists():
        return qid, 'skip'
    if STOP.exists():
        return qid, 'stopped'
    books = 'GS1/GS2' if sub == 'GS' else 'LA（王宽程，优先）/LALU（补充）'
    inp = [msg('developer', prefix),
           msg('user', USER.format(qid=qid, subject='高等数学' if sub == 'GS' else '线性代数', books=books,
                                   stem=q['stem'], answer=q['answer'], solution=q['solution']))]
    body = request_body(cache_key())
    usage = {'input_tokens': 0, 'cached_input_tokens': 0, 'output_tokens': 0, 'reasoning_output_tokens': 0,
             'turns': 0}
    commands, result = [], None
    t0 = time.time()
    budget = [QUESTION_LIMIT]
    phase('start', qid)
    try:
        for turn in range(MAX_TURNS):
            items, u = post({**body, 'input': inp}, budget)
            usage['turns'] += 1
            usage.setdefault('per_turn', []).append({
                'input': u.get('input_tokens', 0),
                'cached': (u.get('input_tokens_details') or {}).get('cached_tokens', 0),
                'output': u.get('output_tokens', 0),
                'reasoning': (u.get('output_tokens_details') or {}).get('reasoning_tokens', 0),
                'item_chars': {t: sum(len(json.dumps(i, ensure_ascii=False)) for i in items if i.get('type') == t)
                               for t in {i.get('type') for i in items}}})
            usage['input_tokens'] += u.get('input_tokens', 0)
            usage['cached_input_tokens'] += (u.get('input_tokens_details') or {}).get('cached_tokens', 0)
            usage['output_tokens'] += u.get('output_tokens', 0)
            usage['reasoning_output_tokens'] += (u.get('output_tokens_details') or {}).get('reasoning_tokens', 0)
            inp += items
            calls = [i for i in items if i.get('type') == 'function_call']
            if not calls:
                text = ''.join(c.get('text', '') for i in items if i.get('type') == 'message'
                               for c in i.get('content', []) if c.get('type') == 'output_text')
                result = json.loads(text)
                break
            for c in calls:
                args = json.loads(c['arguments']).get('args', '')
                phase(f'tool (turn {turn + 1}): {args[:60]}')
                output = run_tool(args)
                commands.append({'command': args, 'output_chars': len(output)})
                inp.append({'type': 'function_call_output', 'call_id': c['call_id'], 'output': output})
            usage['per_turn'][-1]['tool_output_chars'] = sum(len(i['output']) for i in inp[-len(calls):])
        if result is None:
            raise RuntimeError(f'no final answer after {MAX_TURNS} turns')
    except Exception as e:  # noqa: BLE001 - recorded per question, the run continues
        save(out_dir / f'{qid}.err.txt', f'{type(e).__name__}: {e}')
        return qid, f'failed: {str(e)[:150]}'
    jsonsave(out, {'question_id': qid, 'subject': sub, 'year': q['year'], 'label': q['label'],
                   'engine': 'direct-responses', 'usage': usage, 'seconds': round(time.time() - t0, 1),
                   'finished': datetime.now(timezone.utc).isoformat(), 'commands': commands, **result})
    (out_dir / f'{qid}.err.txt').unlink(missing_ok=True)
    _last_done[0] = time.monotonic()
    phase('idle')
    return qid, (f'{len(result["citations"])} citations, {usage["turns"]} turns, in {usage["input_tokens"]} '
                 f'(cached {usage["cached_input_tokens"]}), out {usage["output_tokens"]}')


STOP = mq.OUT / 'STOP'
API_LOCK = mq.OUT / '.api_process.lock'


def single_api_process():
    """Refuse to start while another API-calling process (mapping or review) runs: the user's limit is at most
    WORKERS concurrent requests in total, and two processes would double it."""
    import fcntl
    f = open(API_LOCK, 'a+')
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.seek(0)
        sys.exit(f'another API process is running ({f.read().strip() or "unknown pid"}); not starting')
    f.seek(0)
    f.truncate()
    f.write(f'pid {os.getpid()}: {" ".join(sys.argv)}')
    f.flush()
    return f  # keep the handle open: the lock lasts as long as the process


def main(args):
    out_dir = mq.OUT / 'raw'
    if '--out' in args:
        i = args.index('--out')
        out_dir = Path(args[i + 1])
        args = args[:i] + args[i + 2:]
    out_dir.mkdir(parents=True, exist_ok=True)
    subjects = [a for a in args if a in ('GS', 'LA')]
    ids = [a for a in args if a.startswith('math2-')]
    qs = [q for q in mq.questions() if q['_subject'] in subjects or q['question_id'] in ids]
    _lock = single_api_process()  # noqa: F841
    (mq.OUT / 'run_direct.pid').write_text(str(os.getpid()))
    faulthandler.register(signal.SIGUSR1, file=sys.stdout, all_threads=True)  # kill -USR1 <pid>: dump stacks
    threading.Thread(target=watchdog, daemon=True).start()
    prefix = static_prefix()
    for n in range(1, 6):
        todo = [q for q in qs if not (out_dir / f'{q["question_id"]}.json').exists()]
        if not todo or STOP.exists():
            break
        log(f'pass {n}: {len(todo)} questions to map ({len(qs) - len(todo)} already done)')
        warm_cache(prefix)
        started = []

        def staggered(q):
            # spread the first requests a little
            if len(started) < WORKERS:
                started.append(q['question_id'])
                time.sleep(3 * (len(started) - 1))
            return map_one(q, prefix, out_dir)
        with ThreadPoolExecutor(WORKERS) as ex:
            for qid, status in ex.map(staggered, todo):
                log(qid, status)
        left = sum(not (out_dir / f'{q["question_id"]}.json').exists() for q in todo)
        if left == len(todo):
            log('no progress in this pass, stopping')
            break
    left = [q['question_id'] for q in qs if not (out_dir / f'{q["question_id"]}.json').exists()]
    log(f'finished: {len(qs) - len(left)}/{len(qs)} mapped' + (f', still missing {len(left)}' if left else '')
        + (' (STOP file present)' if STOP.exists() else ''))


if __name__ == '__main__':
    if sys.argv[1:2] == ['run']:
        main(sys.argv[2:])
    else:
        print(__doc__)
