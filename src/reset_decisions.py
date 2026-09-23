"""Explicit user-requested reset; preserve inputs and archive previous decisions."""
from datetime import datetime
import shutil
import uuid
from src.cycle_lock import acquire
from src.live_reasoning import save


def reset(root):
    root=root.resolve()
    with acquire(root) as locked:
        if not locked:raise RuntimeError('Агент выполняет цикл. Дождитесь завершения перед сбросом.')
        folder=root/'data/live'
        identity=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
        archive=folder/'decision_archive'/identity
        archive.mkdir(parents=True)
        names=('approved_actions.json','lifecycle.json')
        for name in names:
            path=(folder/name).resolve()
            if not path.is_relative_to(root):raise ValueError('Reset target outside project')
            if path.exists():shutil.copy2(path,archive/name)
        save(folder/'approved_actions.json',{'actions':[]})
        save(folder/'lifecycle.json',{'incidents':{}})
        save(folder/'decision_reset.json',{'reset_id':identity,'archive':str(archive)})
        clock=folder/'clock.json'
        if clock.exists():clock.unlink()  # a new day starts from 00:00
        return archive
