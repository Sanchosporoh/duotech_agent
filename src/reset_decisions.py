"""Explicit user-requested reset; preserve inputs and archive previous decisions."""
from datetime import datetime
import shutil
import uuid
from src.cycle_lock import acquire
from src.live_reasoning import save


# Saved calculations: kept by a plain reset (fast replay), archived by a fresh one (live recalculation).
CALCULATIONS=('reasoning','plans','network','adaptation','lift_tables','restoration','executions','field_plans','runs')


def reset(root,fresh=False):
    """Start the day again. Decisions, the escalation queue and the last full-calculation basis
    are archived; with fresh=True saved Codex/PROSPER/GAP results are archived too."""
    root=root.resolve()
    with acquire(root) as locked:
        if not locked:raise RuntimeError('Агент выполняет цикл. Дождитесь завершения перед сбросом.')
        folder=root/'data/live'
        identity=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
        archive=folder/'decision_archive'/identity
        archive.mkdir(parents=True)
        names=('approved_actions.json','lifecycle.json','escalations.json','field_basis.json','decision_wait.json')
        for name in names:
            path=(folder/name).resolve()
            if not path.is_relative_to(root):raise ValueError('Reset target outside project')
            if path.exists():shutil.copy2(path,archive/name)
        save(folder/'approved_actions.json',{'actions':[]})
        save(folder/'lifecycle.json',{'incidents':{}})
        for name in ('escalations.json','field_basis.json','decision_wait.json'):
            if (folder/name).exists():(folder/name).unlink()
        if fresh:
            for name in CALCULATIONS:
                if (folder/name).exists():shutil.move(str(folder/name),str(archive/name))
        save(folder/'decision_reset.json',{'reset_id':identity,'archive':str(archive)})
        clock=folder/'clock.json'
        if clock.exists():clock.unlink()  # a new day starts from 00:00
        return archive
