"""Single entry point for external tools: Codex, PROSPER and GAP.

Backend "petex" (default) calls the real tools. Backend "stub" returns
deterministic placeholders so that the whole cycle can run without licenses.
Stub results are marked and are never a PROSPER/GAP result.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
BACKENDS=('petex','stub')
STUB_NOTE='Заглушка инструмента: проверка цепочки, не результат PROSPER/GAP/Codex'


def backend():
    name=os.environ.get('AGENT_TOOL_BACKEND','petex')
    if name not in BACKENDS:raise ValueError(f'Неизвестный режим инструментов: {name}')
    return name


def cache_marker():
    """Extra fingerprint fields: stub and real results never share a cache entry."""
    return {'tool_backend':'stub'} if backend()=='stub' else {}


def guard(root):
    # A stub approval must never reach the engineer's real registry.
    if backend()=='stub' and Path(root).resolve()==REPO:
        raise RuntimeError('Режим заглушек запрещён в рабочем каталоге проекта; используйте отдельную копию')


def ask_codex(root,prompt,schema,cwd):
    guard(root)
    if backend()=='stub':
        from src import tool_stubs
        return tool_stubs.codex(prompt,schema)
    from src.codex_cli import ask_codex as real
    return real(prompt,schema,cwd)


def run_worker(root,script,request,output):
    """Run tools/<script>.py; returns CompletedProcess like subprocess.run."""
    guard(root)
    if backend()=='stub':
        from src import tool_stubs
        tool_stubs.worker(script,Path(request),Path(output))
        return subprocess.CompletedProcess([script],0,STUB_NOTE,'')
    return subprocess.run([sys.executable,str(Path(root)/'tools'/f'{script}.py'),'--request',str(request),'--output',str(output)],
                          cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace')
