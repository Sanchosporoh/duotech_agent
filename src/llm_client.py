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


def provider():
    """('codex', None, None) or (name, model, base_url)."""
    value=os.environ.get('AGENT_LLM','codex').strip() or 'codex'
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


def ask(prompt,schema,model,base_url,key=None,timeout=180):
    """Return (answer, meta). meta: model, seconds, prompt/completion tokens, cost in USD (if reported)."""
    headers={'Content-Type':'application/json'}
    if key:headers['Authorization']='Bearer '+key
    body={'model':model,'messages':[{'role':'user','content':prompt}],'temperature':0.2,
          'response_format':{'type':'json_schema','json_schema':{'name':'answer','strict':True,'schema':_strict(schema)}},
          'usage':{'include':True}}
    started=time.monotonic()
    response=requests.post(base_url+'/chat/completions',headers=headers,json=body,timeout=timeout)
    seconds=round(time.monotonic()-started,2)
    if response.status_code!=200:
        raise RuntimeError(f'LLM {model}: HTTP {response.status_code}: {response.text[:300]}')
    data=response.json()
    usage=data.get('usage') or {}
    meta={'model':model,'seconds':seconds,'prompt_tokens':usage.get('prompt_tokens'),
          'completion_tokens':usage.get('completion_tokens'),'cost_usd':usage.get('cost')}
    content=data['choices'][0]['message']['content']
    try:
        answer=json.loads(content)
    except (TypeError,ValueError) as exc:
        raise ValueError(f'LLM {model}: ответ не JSON') from exc
    jsonschema.validate(answer,schema)   # full schema, including item counts
    return answer,meta
