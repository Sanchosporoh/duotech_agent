"""External action: one Bitrix24 task per approved plan (incoming webhook, tasks.task.add).

Off unless config/bitrix.json has "enabled": true; never in stub mode. The webhook address is a secret:
it is read from the environment and never written to files, logs or error messages.
The task text has no production numbers: decision number, incidents, hour; details stay on the dashboard.
"""
import hashlib
import json
from pathlib import Path


def config(root):
    path=Path(root)/'config'/'bitrix.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def decision_number(action):
    return 'R-'+hashlib.sha1(action['approval_id'].encode('utf-8')).hexdigest()[:8]


def task_fields(action,responsible_id):
    number=decision_number(action)
    return {'TITLE':f'Агент мониторинга: утверждён план компенсации, решение {number}',
            'RESPONSIBLE_ID':responsible_id,
            'DESCRIPTION':f"Решение {number} утверждено инженером в {action['approved_hour']:02d}:00 учебных суток.\n"
                          f"Инциденты: {action['incident_id']}.\nВариант: {action['proposal'].get('title','—')}.\n"
                          'Подробности и расчёт — на витрине агента. Задача создана агентом после утверждения (HITL).'}


def send(root,action):
    """Returns the external record for the action: status 'created' with task_id, 'disabled', 'skipped_stub' or 'error'."""
    from src import llm_client, tool_gateway
    settings=config(root)
    if not settings.get('enabled'):return {'status':'disabled'}
    if tool_gateway.backend()=='stub':return {'status':'skipped_stub'}
    webhook=llm_client.api_key(settings.get('webhook_env','BITRIX_WEBHOOK_URL'))
    if not webhook:return {'status':'error','error':'Не задан адрес вебхука Битрикс24 (переменная окружения BITRIX_WEBHOOK_URL)'}
    import requests
    try:
        response=requests.post(webhook.rstrip('/')+'/tasks.task.add.json',json={'fields':task_fields(action,settings['responsible_id'])},timeout=30)
        body=response.json() if response.content else {}
    except Exception as error:
        # The exception text contains the webhook URL: only its type is reported.
        return {'status':'error','error':f'Битрикс24 недоступен ({type(error).__name__})'}
    task=(body.get('result') or {}).get('task') or {}
    if response.status_code!=200 or not task.get('id'):
        return {'status':'error','error':f"Битрикс24 отклонил задачу: HTTP {response.status_code} {body.get('error_description') or body.get('error') or ''}".strip()}
    return {'status':'created','task_id':str(task['id']),'decision':decision_number(action)}
