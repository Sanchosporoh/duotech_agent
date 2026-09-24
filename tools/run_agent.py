"""Background agent: processes hourly measurements without the dashboard.

Examples (project venv):
  python tools/run_agent.py --once                         one new hour (simulated clock)
  python tools/run_agent.py --loop --interval 60           demo: one hour per minute until 23:00
  python tools/run_agent.py --loop --interval 10 --stop-at 6   demo: stop after 06:00 to show the decision
  python tools/run_agent.py --loop --clock wall --interval 300   real time: current hour every 5 min
  python tools/run_agent.py --root <copy> --backend stub --loop   whole chain without licenses
  python tools/run_agent.py --reset [--fresh]              new day; --fresh also recalculates everything live

Windows Task Scheduler can call "--once" (simulated) or "--once --clock wall" on a schedule.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))


def main():
    parser=argparse.ArgumentParser(description='Фоновый почасовой агент мониторинга добычи')
    parser.add_argument('--root',type=Path,default=REPO,help='каталог проекта (для заглушек — отдельная копия)')
    parser.add_argument('--clock',choices=['simulated','wall'],default='simulated')
    parser.add_argument('--backend',choices=['petex','stub'],help='режим инструментов; по умолчанию из AGENT_TOOL_BACKEND')
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--once',action='store_true',help='один такт')
    mode.add_argument('--loop',action='store_true',help='такты с паузой --interval')
    mode.add_argument('--reset',action='store_true',help='начать сутки заново: решения, эскалации и часы агента в архив')
    parser.add_argument('--fresh',action='store_true',help='вместе с --reset: убрать и сохранённые расчёты, чтобы Codex, PROSPER и GAP посчитали заново')
    parser.add_argument('--interval',type=float,default=60.,help='пауза между тактами, с')
    parser.add_argument('--stop-at',type=int,help='остановиться после обработки этого часа (демонстрация)')
    args=parser.parse_args()
    if args.backend:os.environ['AGENT_TOOL_BACKEND']=args.backend
    from src import cycle_service
    root=args.root.resolve()
    if args.reset:
        from src.reset_decisions import reset
        archive=reset(root,fresh=args.fresh)
        print('Сутки начнутся с 00:00. Архив:',archive,'· сохранённые расчёты',('убраны — будет живой расчёт' if args.fresh else 'сохранены — быстрый повтор'));return
    while True:
        result=cycle_service.tick(root,args.clock)
        print(json.dumps({k:result.get(k) for k in ('hour','status','incidents','errors','duration_seconds')},ensure_ascii=False),flush=True)
        if not args.loop or result['status']=='day_finished':break
        if args.clock=='simulated' and result['hour']>=cycle_service.LAST_HOUR:break
        if args.stop_at is not None and result['hour']>=args.stop_at:break
        time.sleep(args.interval)


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    main()
