"""Wall-clock retry for unavailable PetEx licenses, shared across calculations."""
from datetime import datetime,timezone
import json
import re
import time
import subprocess
from src.live_reasoning import save
from src.cycle_lock import acquire


def state(root):
    path=root/'data/live/license_wait.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


BUSY_MARKERS=('PROSPER уже открыт','GAP уже открыт','Другой расчёт PetEx ещё работает')
PETEX_BUSY_REASON='PetEx занят другим расчётом (открыт PROSPER или GAP). Агент не закрывает чужие окна и повторит расчёт в следующем такте после их закрытия.'


def is_petex_busy(message):
    return any(marker in message for marker in BUSY_MARKERS)


def petex_running():
    for executable in ('prosper.exe','gap.exe'):
        processes=subprocess.run(['tasklist','/FI',f'IMAGENAME eq {executable}','/FO','CSV','/NH'],capture_output=True,text=True,errors='replace')
        if processes.returncode==0 and executable in processes.stdout.lower():return True
    return False


OPENSERVER_MESSAGES={'Variable name was not found':'PetEx не вернул результат расчёта (OpenServer: переменная результата не найдена — расчёт не выполнен или прерван)'}


def readable(message):
    """The engineer sees the cause in one line; the traceback stays in 'error' for diagnostics."""
    lines=[line.strip() for line in str(message).splitlines() if line.strip()]
    if not lines:return 'Расчёт PetEx завершился без сообщения об ошибке'
    last=lines[-1]
    match=re.match(r'^[\w.]+(?:Error|Exception): (.*)$',last)
    text=match.group(1) if match else last
    for marker,explanation in OPENSERVER_MESSAGES.items():
        if marker in text:return explanation
    return 'Ошибка расчёта PetEx: '+text


def _retry_marker(attempt):
    return attempt.with_name('auto_retry.json')


def is_license_error(message):
    return 'no openserver license available' in message.lower() or 'недоступна лицензия openserver' in message.lower()


def blocked(root,attempt=None,now=None):
    waiting=state(root)
    if waiting.get('stage')=='waiting_license' and (time.time() if now is None else now)<waiting['retry_at_epoch']:
        return waiting
    if attempt and attempt.exists():
        previous=json.loads(attempt.read_text(encoding='utf-8'))
        if previous.get('stage')=='running':
            with acquire(root,'petex.lock') as free:
                if free:return None
            return {'stage':'running','reason':'Расчёт PetEx ещё выполняется. Его длительность не является признаком зависания.'}
        if previous.get('stage')=='completed':
            return {'stage':'needs_attention','reason':'Расчёт отмечен завершённым, но его результат отсутствует или повреждён. Нужен повторный расчёт; использовать этот результат нельзя.'}
        if previous.get('stage')=='retry_requested':return None
        if previous.get('stage')=='calculation_failed':
            # One automatic retry per calculation input; a second failure goes to the engineer.
            save(_retry_marker(attempt),{'previous_error':previous.get('error','')})
            return None
        if previous.get('stage')=='waiting_petex':
            return previous if petex_running() else None
        message=previous.get('error',previous.get('reason',''))
        for executable in ('prosper.exe','gap.exe'):
            if previous.get('stage')=='needs_attention' and f"is_process_running('{executable}')" in message:
                processes=subprocess.run(['tasklist','/FI',f'IMAGENAME eq {executable}','/FO','CSV','/NH'],capture_output=True,text=True,errors='replace')
                if processes.returncode==0 and executable not in processes.stdout.lower():return None
        if previous.get('stage')=='needs_attention' and is_license_error(previous.get('error',previous.get('reason',''))):
            retry=failure(root,previous.get('error',previous.get('reason','')),now)
            save(attempt,retry)
            return retry
        if previous.get('stage')!='waiting_license':return previous
    return None


def failure(root,message,now=None,attempt=None):
    if is_petex_busy(message):
        return {'stage':'waiting_petex','reason':PETEX_BUSY_REASON,'error':message}
    if not is_license_error(message):
        if attempt is not None and not _retry_marker(attempt).exists():
            return {'stage':'calculation_failed','reason':readable(message)+'. Агент повторит расчёт в следующем такте.','error':message}
        prefix='Повторный расчёт тоже не удался. ' if attempt is not None else ''
        return {'stage':'needs_attention','reason':prefix+readable(message)+'. Нужна проверка модели инженером-моделистом.','error':message}
    policy=json.loads((root/'config/license_retry.json').read_text(encoding='utf-8'))
    count=state(root).get('failure_count',0)+1
    delay=min(policy['maximum_delay_seconds'],policy['initial_delay_seconds']*2**min(count-1,20))
    retry=(time.time() if now is None else now)+delay
    result={'stage':'waiting_license','failure_count':count,'retry_at_epoch':retry,
        'retry_at':datetime.fromtimestamp(retry,timezone.utc).astimezone().isoformat(timespec='seconds'),
        'reason':'Недоступна лицензия OpenServer. Расчёт не выполнен; агент ожидает автоматической повторной попытки.',
        'error':message,'delay_seconds':delay}
    save(root/'data/live/license_wait.json',result)
    return result


def success(root):
    if state(root):save(root/'data/live/license_wait.json',{'stage':'available','failure_count':0})
