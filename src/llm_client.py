"""OpenAI-compatible chat API with strict JSON schema: OpenRouter or a local LM Studio server.

Selected by AGENT_LLM:
  codex                         Codex CLI, model of the account by default
  codex:<model>                 Codex CLI with a pinned model, e.g. codex:gpt-6-sol
  openrouter:<model>            e.g. openrouter:openai/gpt-4o-mini; key in OPENROUTER_API_KEY
  lmstudio:<model>@<base_url>   e.g. lmstudio:qwen2.5-7b@http://server:1234/v1 (no key)

The key is read from the environment or, on Windows, from the user environment
(HKCU\\Environment) so that a key set with SetEnvironmentVariable works without a restart.
It is never printed or written to files.
"""
import copy
import json
import os
import time
import jsonschema
import requests

OPENROUTER_URL='https://openrouter.ai/api/v1'


POLICY=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'config','llm_policy.json')


def policy(path=POLICY):
    """Which providers the company contour allows and the default model (config/llm_policy.json)."""
    if not os.path.exists(path):return {}
    with open(path,encoding='utf-8') as stream:return json.load(stream)


def provider():
    """('codex', None, None) or (name, model, base_url)."""
    value=os.environ.get('AGENT_LLM','').strip() or policy().get('default') or 'codex'
    if value=='codex':return 'codex',None,None
    if value.startswith('codex:') and value[6:].strip():return 'codex',value[6:].strip(),None
    name,_,rest=value.partition(':')
    if name=='openrouter' and rest:return 'openrouter',rest,OPENROUTER_URL
    if name=='lmstudio' and '@' in rest:
        model,_,url=rest.partition('@');return 'lmstudio',model,url.rstrip('/')
    raise ValueError('AGENT_LLM: ожидается codex, codex:<модель>, openrouter:<модель> или lmstudio:<модель>@<адрес>')


def api_key(name='OPENROUTER_API_KEY'):
    key=os.environ.get(name)
    if not key and os.name=='nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as handle:
                key=winreg.QueryValueEx(handle,name)[0]
        except OSError:
            key=None
    return key


def _strict(schema):
    """Structured outputs of some providers reject minItems/maxItems; they are checked locally instead."""
    schema=copy.deepcopy(schema)
    def walk(node):
        if isinstance(node,dict):
            node.pop('minItems',None);node.pop('maxItems',None)
            for value in node.values():walk(value)
        elif isinstance(node,list):
            for value in node:walk(value)
    walk(schema)
    return schema


def _read_whole(response):
    data=response.json()
    return data['choices'][0]['message']['content'],data.get('usage') or {}


def _read_stream(response,model,started,timeout):
    """Server-sent events: the answer is the sum of content deltas; reasoning deltas only keep the line alive."""
    parts,usage=[],{}
    # Bytes, decoded per line: event-stream has no charset, and text decoding would split Cyrillic on U+0085.
    for raw in response.iter_lines():
        if time.monotonic()-started>timeout:
            response.close();raise requests.Timeout()
        line=raw.decode('utf-8') if isinstance(raw,bytes) else raw
        if not line.startswith('data:'):continue
        chunk=line[5:].strip()
        if chunk=='[DONE]':break
        event=json.loads(chunk)
        usage=event.get('usage') or usage
        for choice in event.get('choices') or []:
            parts.append((choice.get('delta') or {}).get('content') or '')
    return ''.join(parts),usage


def ask(prompt,schema,model,base_url,key=None,timeout=None,stream=False):
    """Return (answer, meta). meta: model, seconds, prompt/completion tokens, cost in USD (if reported)."""
    headers={'Content-Type':'application/json'}
    if key:headers['Authorization']='Bearer '+key
    body={'model':model,'messages':[{'role':'user','content':prompt}],'temperature':0.2,
          'response_format':{'type':'json_schema','json_schema':{'name':'answer','strict':True,'schema':_strict(schema)}},
          'usage':{'include':True}}
    started=time.monotonic()
    # A local model on the company server is slower than a cloud one: the limit is set by LLM_TIMEOUT_SECONDS.
    timeout=timeout or float(os.environ.get('LLM_TIMEOUT_SECONDS',180))
    if stream:
        # A slow local model answers for many minutes; a silent connection is cut by the network after ~10 min idle
        # (two calls broke at exactly 600 s, 06.10). Streaming keeps bytes flowing while the model reasons.
        body['stream']=True;body['stream_options']={'include_usage':True}
    try:
        response=requests.post(base_url+'/chat/completions',headers=headers,json=body,timeout=timeout,stream=stream)
        if response.status_code!=200:
            if response.status_code==403 and 'security policy' in response.text.lower():
                raise RuntimeError(f'LLM {model}: провайдер отказал в доступе (HTTP 403, «Access denied by security policy») — ограничение сети или политики провайдера')
            raise RuntimeError(f'LLM {model}: HTTP {response.status_code}: {response.text[:300]}')
        content,usage=_read_stream(response,model,started,timeout) if stream else _read_whole(response)
    except requests.Timeout as exc:
        raise RuntimeError(f'LLM {model}: сервер не ответил за {timeout:g} с') from exc
    except requests.RequestException as exc:
        raise RuntimeError(f'LLM {model}: сервер LLM недоступен — соединение разорвано или отклонено; проверьте, что сервер запущен и модель загружена') from exc
    seconds=round(time.monotonic()-started,2)
    meta={'model':model,'seconds':seconds,'prompt_tokens':usage.get('prompt_tokens'),
          'completion_tokens':usage.get('completion_tokens'),'cost_usd':usage.get('cost')}
    try:
        answer=json.loads(content)
    except (TypeError,ValueError) as exc:
        raise ValueError(f'LLM {model}: ответ не JSON') from exc
    try:
        jsonschema.validate(answer,schema)   # full schema, including item counts
    except jsonschema.ValidationError as exc:
        # A bad answer, not a tool failure: one readable line, the answer itself is not dumped to the engineer.
        where='.'.join(str(p) for p in exc.absolute_path) or 'ответ'
        raise ValueError(f'LLM {model}: ответ не прошёл проверку схемы ({where}: {exc.validator} {exc.validator_value})') from exc
    return answer,meta
