"""Local escalation queue: what the agent could not resolve goes to a person with a deadline.

MVP: the queue is a local file; nothing is sent. Addressee and deadlines come from
config/escalation.json (table Р2). Deadlines are counted in calendar hours here.
"""
from datetime import datetime, timedelta
import json
import uuid
from src.live_reasoning import save


def _path(root):
    return root/'data'/'live'/'escalations.json'


def load(root):
    path=_path(root)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'items':[]}


def raise_item(root,subject,reason,run_id,hour,now=None,kind='agent'):
    """Add an open item unless the same subject and reason are already waiting.

    kind='agent' — the agent could not finish (owner: modelling engineer);
    kind='decision' — a ready proposal waits for the engineer's decision too long (owner: field technologist).
    """
    data=load(root)
    for item in data['items']:
        if item['status']=='open' and item['subject']==subject and item['reason']==reason:
            return item
    policy=json.loads((root/'config'/'escalation.json').read_text(encoding='utf-8'))
    now=now or datetime.now()
    prefix='decision_' if kind=='decision' else ''
    owner,hours=policy[prefix+'owner_role'],policy[prefix+'response_hours']
    backup,extra=policy[prefix+'backup_role'],policy[prefix+'backup_response_hours']
    item={'id':uuid.uuid4().hex[:8],'status':'open','kind':kind,'subject':subject,'reason':reason,'run_id':run_id,'hour':hour,
          'created_at':now.isoformat(timespec='seconds'),
          'owner_role':owner,'deadline':(now+timedelta(hours=hours)).isoformat(timespec='minutes'),
          'backup_role':backup,'backup_deadline':(now+timedelta(hours=hours+extra)).isoformat(timespec='minutes')}
    if kind=='decision':
        # The wait is counted in agent hours: the item is raised when the owner's time is over,
        # the backup role takes over after the backup time.
        item.update(deadline_hour=hour+extra,deadline=f'{(hour+extra)%24:02d}:00 (час агента)',backup_deadline=None)
    data['items'].append(item)
    save(_path(root),data)
    return item


def close(root,item_id,outcome):
    data=load(root)
    for item in data['items']:
        if item['id']==item_id:
            item.update(status='closed',outcome=outcome,closed_at=datetime.now().isoformat(timespec='seconds'))
    save(_path(root),data)


def open_items(root,now=None,agent_hour=None):
    now=now or datetime.now()
    items=[dict(i) for i in load(root)['items'] if i['status']=='open']
    for item in items:
        # After the owner's deadline the same item is shown to the backup role.
        if 'deadline_hour' in item:
            item['overdue']=agent_hour is not None and agent_hour>=item['deadline_hour']
        else:
            item['overdue']=now>datetime.fromisoformat(item['deadline'])
        item['current_role']=item['backup_role'] if item['overdue'] else item['owner_role']
    return items
