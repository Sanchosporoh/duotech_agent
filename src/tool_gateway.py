"""Single entry point for external tools: Codex, PROSPER and GAP.

Backend "petex" (default) calls the real tools. Backend "stub" returns
deterministic placeholders so that the whole cycle can run without licenses.
Stub results are marked and are never a PROSPER/GAP result.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
BACKENDS=('petex','stub')
STUB_NOTE='Заглушка инструмента: проверка цепочки, не результат PROSPER/GAP/Codex'


# Kind of limit for each external tool; see config/cycle_limits.json.
WORKER_KIND={'run_live_gap':'gap_runs','fit_live_prosper':'prosper_runs','export_live_vlp':'prosper_runs'}
LIMIT_LABEL={'llm_calls':'вызовы LLM','gap_runs':'запуски GAP','prosper_runs':'запуски PROSPER'}
_tick=None


class LimitExceeded(RuntimeError):
    """The tick used up its budget of external calls; the cycle stops and escalates."""


def start_tick(root):
    """Open the per-tick counters. One tick runs at a time under the project cycle lock."""
    global _tick
    path=Path(root)/'config'/'cycle_limits.json'
    limits=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    _tick={'limits':limits,'llm_calls':0,'gap_runs':0,'prosper_runs':0,'llm_prompt_chars':0,'calls':[],
           'day':_used_today(Path(root))}


def _used_today(root):
    """Calls already spent today according to the run journal (daily budget, protects against cost attacks)."""
    from datetime import date
    used={'llm_calls':0,'gap_runs':0,'prosper_runs':0}
    today=date.today().isoformat()
    for path in (root/'data'/'live'/'runs').glob(today.replace('-','')+'-*.json'):
        try:tools=json.loads(path.read_text(encoding='utf-8')).get('tools',{})
        except (OSError,ValueError):continue
        for kind in used:used[kind]+=tools.get(kind,0) or 0
    return used


def finish_tick():
    """Close the counters and return what the tick used: the basis of the run journal and cost."""
    global _tick
    tick,_tick=_tick,None
    if tick is None:return {}
    tokens=round(tick['llm_prompt_chars']/4)
    price=tick['limits'].get('llm_price_per_1k_tokens_rub')
    seconds={}
    for call in tick['calls']:seconds[call['tool']]=round(seconds.get(call['tool'],0)+call['seconds'],3)
    reported=[c for c in tick['calls'] if c.get('prompt_tokens') is not None]
    return {'llm_calls':tick['llm_calls'],'gap_runs':tick['gap_runs'],'prosper_runs':tick['prosper_runs'],
            'llm_tokens_reported':{'prompt':sum(c['prompt_tokens'] or 0 for c in reported),'completion':sum(c['completion_tokens'] or 0 for c in reported)} if reported else None,
            'llm_cost_usd':round(sum(c.get('cost_usd') or 0 for c in reported),6) if reported else None,
            'llm_prompt_tokens_estimate':tokens,'llm_cost_rub':None if price is None else round(tokens/1000*price,2),
            'tool_seconds':seconds,'failed_calls':[c for c in tick['calls'] if not c['ok']],
            'limit_exceeded':tick.get('limit_exceeded')}


def set_open_incidents(count):
    """The LLM limit of a tick depends on how many incidents are diagnosed in it."""
    if _tick is not None:_tick['open_incidents']=count


def tick_limit(kind):
    limits=_tick['limits']
    if kind=='llm_calls' and 'llm_calls_per_incident' in limits:
        return limits['llm_calls_per_incident']*_tick.get('open_incidents',1)+limits['llm_calls_per_plan']
    return limits.get('max_'+kind)


def _count(kind):
    if _tick is None:return
    limit=tick_limit(kind)
    if limit is not None and _tick[kind]>=limit:
        message=f'Превышен лимит такта: {LIMIT_LABEL[kind]} — не более {limit}. Цикл остановлен и передан инженеру.'
        _tick['limit_exceeded']=message
        raise LimitExceeded(message)
    daily=_tick['limits'].get(f'max_{kind}_per_day')
    if daily is not None and _tick['day'].get(kind,0)+_tick[kind]>=daily:
        message=f'Исчерпан суточный бюджет: {LIMIT_LABEL[kind]} — не более {daily} за сутки. Цикл остановлен и передан инженеру.'
        _tick['limit_exceeded']=message
        raise LimitExceeded(message)
    _tick[kind]+=1


def _record(tool,started,ok,**extra):
    if _tick is not None:
        _tick['calls'].append(dict(tool=tool,seconds=round(time.monotonic()-started,3),ok=ok,**extra))


def _stub_delay():
    # Optional pause for stub demos: makes each step visible on the dashboard.
    time.sleep(float(os.environ.get('AGENT_STUB_DELAY','0') or 0))


def backend():
    name=os.environ.get('AGENT_TOOL_BACKEND','petex')
    if name not in BACKENDS:raise ValueError(f'Неизвестный режим инструментов: {name}')
    return name


def cache_marker():
    """Extra fingerprint fields: stub/real results and different LLMs never share a cache entry."""
    marker={'tool_backend':'stub'} if backend()=='stub' else {}
    from src import llm_client
    name,model,_=llm_client.provider()
    if name!='codex':marker['llm']=f'{name}:{model}'
    return marker


def guard(root):
    # A stub approval must never reach the engineer's real registry.
    if backend()=='stub' and Path(root).resolve()==REPO:
        raise RuntimeError('Режим заглушек запрещён в рабочем каталоге проекта; используйте отдельную копию')


def ask_codex(root,prompt,schema,cwd):
    guard(root)
    _count('llm_calls')
    if _tick is not None:_tick['llm_prompt_chars']+=len(prompt)
    started=time.monotonic()
    try:
        if backend()=='stub':
            from src import tool_stubs
            _stub_delay()
            answer=tool_stubs.codex(prompt,schema)
        else:
            from src import llm_client
            name,model,url=llm_client.provider()
            if name=='codex':
                from src.codex_cli import ask_codex as real
                answer=real(prompt,schema,cwd);meta={}
            else:
                answer,meta=llm_client.ask(prompt,schema,model,url,llm_client.api_key() if name=='openrouter' else None)
    except Exception:
        _record('llm',started,False,prompt_chars=len(prompt));raise
    _record('llm',started,True,prompt_chars=len(prompt),**{k:v for k,v in (meta if backend()!='stub' else {}).items() if k!='seconds'})
    return answer


def run_worker(root,script,request,output):
    """Run tools/<script>.py; returns CompletedProcess like subprocess.run."""
    guard(root)
    _count(WORKER_KIND[script])
    started=time.monotonic()
    if backend()=='stub':
        from src import tool_stubs
        _stub_delay()
        try:tool_stubs.worker(script,Path(request),Path(output))
        except Exception:
            _record(script,started,False);raise
        completed=subprocess.CompletedProcess([script],0,STUB_NOTE,'')
    else:
        # A live PetEx calculation is never killed by time: a killed worker leaves GAP/PROSPER open.
        completed=subprocess.run([sys.executable,str(Path(root)/'tools'/f'{script}.py'),'--request',str(request),'--output',str(output)],
                                 cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace')
    _record(script,started,completed.returncode==0)
    return completed
