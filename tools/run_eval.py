"""Eval suite of the agent (course criterion 6.1): 15 cases, expected result and automatic check.

Every case runs on an isolated project copy with tool stubs (no Codex, no PetEx, no cost),
so the suite checks the agent's behaviour and control logic, reproducibly. LLM answer quality
is evaluated separately on real models: tools/compare_llm.py.

Run:  python tools/run_eval.py --label after
Result: course/eval/<label>.json and course/eval/<label>.md
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
os.environ['AGENT_TOOL_BACKEND']='stub'
import pandas as pd
from tests.support import FIRST, SECOND, make_project
from src import autonomous_cycle, cycle_service, escalation, incident_lifecycle, incident_view, live_execution


def ticks(root,count):
    runs=[]
    for _ in range(count):runs.append(cycle_service.tick(root))
    return runs


def state(root,hour,incident):
    separator,telemetry,_=cycle_service.load_measurements(root)
    return autonomous_cycle.read_states(root,separator,telemetry,hour,incident_view.opened_incidents(separator,hour)).get(incident,{})


def edit_csv(root,name,change):
    path=root/'data/live'/name
    frame=pd.read_csv(path);change(frame);frame.to_csv(path,index=False)


def set_config(root,name,**values):
    path=root/'config'/name
    data=json.loads(path.read_text(encoding='utf-8'));data.update(values)
    path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')


def approve(root,hour,incident):
    item=state(root,hour,incident)
    live_execution.approve(root,item['field_plan']['incidents'],hour,item['fingerprint'],item['recommendation'],True)
    incident_lifecycle.record_decision(root/'data/live/lifecycle.json',incident,'Утверждено','',item['recommendation']['selected']['title'],'eval')


def calls(run):
    tools=run.get('tools',{})
    return tools.get('llm_calls',0),tools.get('gap_runs',0)


# ---- cases: each returns (passed, observed) ----

def e01(root):
    run=ticks(root,1)[0]
    return run['status']=='no_incidents' and calls(run)==(0,0),f"статус {run['status']}, LLM/GAP {calls(run)}"


def e02(root):
    run=ticks(root,7)[-1];item=state(root,6,FIRST)
    wells={w for h in item.get('hypotheses',{}).get('hypotheses',[]) for w in h['candidate_wells']}
    ok=item.get('stage')=='awaiting_human_decision' and item['recommendation'].get('ready') and 'W_BEL_27_TLBB' in wells
    return ok,f"стадия {item.get('stage')}, W27 среди кандидатов: {'W_BEL_27_TLBB' in wells}, остаток {item.get('recommendation',{}).get('selected',{}).get('expected_deficit_t')}"


def e03(root):
    ticks(root,7);approve(root,6,FIRST);ticks(root,9)
    item=state(root,15,SECOND);plan=item.get('plan',{})
    selected={w for a in plan.get('proposal',{}).get('alternatives',[]) for w in a['selected_wells']}
    ok=item.get('stage')=='awaiting_human_decision' and 'W_BEL_22_TLBB' not in selected and plan.get('need',{}).get('estimated_hours')==[11,12]
    return ok,f"стадия {item.get('stage')}, W22 в наборах: {'W_BEL_22_TLBB' in selected}, оценённые часы {plan.get('need',{}).get('estimated_hours')}"


def deviation(pct):
    def case(root):
        def change(frame):
            plan=frame.loc[frame.hour==6,'plan_oil_tpd']
            frame.loc[frame.hour>=6,'separator_oil_tpd']=float(plan.iloc[0])*(1+pct/100)
        edit_csv(root,'separator.csv',change)
        run=ticks(root,7)[-1]
        opened=not incident_view.opened_incidents(cycle_service.load_measurements(root)[0],6).empty
        return opened,f"отклонение {pct} %, инцидент открыт: {opened}, статус {run['status']}"
    return case


def e04(root):
    opened,observed=deviation(-4.9)(root)
    return not opened,observed


def e05(root):
    return deviation(-5.0)(root)


def e06(root):
    ticks(root,14);item=state(root,13,FIRST);need=item.get('plan',{}).get('need',{})
    ok=item.get('stage')=='awaiting_human_decision' and need.get('estimated_hours')==[11,12]
    return ok,f"стадия {item.get('stage')}, оценённые часы {need.get('estimated_hours')}, диапазон {need.get('net_deficit_range_t')}"


def e07(root):
    run=ticks(root,8)[-1];level=run['incidents'].get(FIRST,{}).get('recompute')
    return level=='none' and calls(run)==(0,0),f"уровень пересчёта {level}, LLM/GAP {calls(run)}"


def e08(root):
    ticks(root,7);plan=state(root,6,FIRST).get('plan',{})
    sets=plan.get('proposal',{}).get('alternatives',[])
    ok=bool(sets) and all('W_BEL_50_TLBB' in a['selected_wells'] for a in sets)
    return ok,f"W50 в каждом наборе: {ok}, обязательная корректировка: {[m['well_id'] for m in plan.get('mandatory_wells',[])]}"


def e09(root):
    edit_csv(root,'separator.csv',lambda f:f.__setitem__('plan_oil_tpd',f.plan_oil_tpd.where(f.hour!=3,-1)))
    run=ticks(root,7)[-1];items=escalation.open_items(root)
    ok=run['status']=='invalid_input' and calls(run)==(0,0) and bool(items)
    return ok,f"статус {run['status']}, LLM/GAP {calls(run)}, эскалаций {len(items)}: {(run.get('errors') or [''])[0][:60]}"


def e10(root):
    def change(frame):
        frame['sensor_pressure_bar']=frame['sensor_pressure_bar'].astype(object)
        frame.loc[frame.index[5],'sensor_pressure_bar']='нет связи'
    edit_csv(root,'telemetry.csv',change)
    run=ticks(root,7)[-1]
    return run['status']=='invalid_input' and calls(run)==(0,0),f"статус {run['status']}: {(run.get('errors') or [''])[0][:70]}"


def e11(root):
    run=ticks(root,12)[-1];stage=run['incidents'].get(FIRST,{}).get('stage')
    # The proposal of 06:00 waits for a decision and is escalated for that; missing data itself is not escalated.
    data_items=[i for i in escalation.open_items(root) if i['kind']=='agent']
    ok=stage=='needs_data' and calls(run)==(0,0) and not data_items and not run['escalations']
    return ok,f"11:00 стадия {stage}, LLM/GAP {calls(run)}, эскалаций из-за нет данных: {len(data_items)}"


def e12(root):
    from src import tool_stubs
    real=tool_stubs.codex
    def invented(prompt,schema):
        answer=real(prompt,schema)
        if 'hypotheses' in schema['properties']:answer['hypotheses'][0]['candidate_wells']=['W_BEL_99_FAKE']
        return answer
    with patch('src.tool_stubs.codex',side_effect=invented):run=ticks(root,7)[-1]
    stage=run['incidents'].get(FIRST,{}).get('stage');items=escalation.open_items(root)
    ok=stage=='needs_attention' and any('неизвестные скважины' in i['reason'] for i in items) and calls(run)[1]==0
    return ok,f"стадия {stage}, GAP {calls(run)[1]}, эскалация: {items[0]['reason'][:60] if items else '—'}"


def e13(root):
    set_config(root,'network_constraints.json',minimum_fbhp_bar=200.)
    run=ticks(root,7)[-1];items=escalation.open_items(root)
    ok=any('GAP: нет допустимого варианта' in i['reason'] for i in items)
    return ok,f"стадия {run['incidents'].get(FIRST,{}).get('stage')}, эскалаций {len(items)}{': '+items[0]['reason'][:70] if items else ''}"


def e14(root):
    set_config(root,'cycle_limits.json',max_llm_calls_per_day=4)
    stopped=None
    for run in (cycle_service.tick(root) for _ in range(12)):
        if run.get('incidents',{}).get(FIRST,{}).get('stage')=='awaiting_human_decision':
            incident_lifecycle.record_decision(root/'data/live/lifecycle.json',FIRST,'На доработке',f"комментарий {run['hour']}",None,'eval')
        if run.get('tools',{}).get('limit_exceeded'):stopped=run;break
    items=escalation.open_items(root)
    ok=stopped is not None and 'суточный бюджет' in stopped['tools']['limit_exceeded'] and bool(items)
    return ok,f"остановка в {stopped['hour'] if stopped else '—'}:00: {stopped['tools']['limit_exceeded'][:60] if stopped else 'нет'}"


def e15(root):
    ticks(root,9)   # ready at 06:00, no decision until 08:00
    first=[(i['kind'],i['current_role']) for i in escalation.open_items(root,agent_hour=8)]
    ticks(root,2)   # 10:00
    later=[i['current_role'] for i in escalation.open_items(root,agent_hour=10)]
    ok=first==[('decision','инженер-моделист')] and later==['руководитель группы моделирования и оптимизации']
    return ok,f"08:00 → {first}; 10:00 → {later}"


CASES=[
    ('E01','типовой','Нормальный час без отклонения (00:00)','Инцидента нет, ни одного вызова LLM и GAP',e01),
    ('E02','типовой','Выход за −5 % в 06:00 (износ ЭЦН W27)','Инцидент, W27 среди гипотез, готовое допустимое предложение, ждёт решения инженера',e02),
    ('E03','типовой','Второй инцидент в 15:00 после утверждения первого (остановка W22)','Собственный план: W22 не регулируется, пропуск факта 11–12 ч оценён, предложение ждёт решения',e03),
    ('E04','пограничный','Отклонение −4.9 %','Инцидент не открывается',e04),
    ('E05','пограничный','Отклонение ровно −5.0 %','Инцидент открывается (граница включительно)',e05),
    ('E06','пограничный','Пропуск факта сепаратора в прошлом (11–12 ч), расчёт в 13:00','План строится, пропущенные часы оценены диапазоном',e06),
    ('E07','пограничный','Час без существенных изменений (07:00)','Без пересчёта: 0 вызовов LLM и GAP',e07),
    ('E08','пограничный','Скважина уже нарушает Pзаб в текущем состоянии (W50)','W50 добавлена в каждый набор как обязательная корректировка',e08),
    ('E09','невалидный вход','Отрицательный план в CSV сепаратора','Расчёт не запускается, «некорректный вход», эскалация',e09),
    ('E10','невалидный вход','Текст в числовом поле телеметрии','Расчёт не запускается, понятная ошибка',e10),
    ('E11','невалидный вход','Нет факта сепаратора в текущем часу (11:00)','«Нет данных», 0 вызовов, отсутствие данных не эскалируется (автоожидание)',e11),
    ('E12','отказ / эскалация','LLM назвала несуществующую скважину','Ответ отбракован, GAP не запускается, эскалация инженеру-моделисту',e12),
    ('E13','отказ / эскалация','GAP: ни один вариант не проходит ограничения','Эскалация «GAP: нет допустимого варианта» инженеру-моделисту',e13),
    ('E14','отказ / эскалация','Возврат с комментарием каждый час (cost-attack)','Суточный бюджет останавливает агента, эскалация',e14),
    ('E15','отказ / эскалация','Готовое предложение без решения','Через 2 ч — инженеру-моделисту, через 4 ч — руководителю группы',e15),
]


def run_case(case):
    code,category,scenario,expected,check=case
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        root=make_project(directory)
        started=time.monotonic()
        try:passed,observed=check(root)
        except Exception as exc:passed,observed=False,f'сбой: {type(exc).__name__}: {str(exc)[:120]}'
        journal=list((root/'data/live/runs').glob('*.json'))
        totals={'llm_calls':0,'gap_runs':0,'errors':0}
        for path in journal:
            run=json.loads(path.read_text(encoding='utf-8'))
            totals['llm_calls']+=run.get('tools',{}).get('llm_calls',0) or 0
            totals['gap_runs']+=run.get('tools',{}).get('gap_runs',0) or 0
            totals['errors']+=bool(run.get('errors')) or run['status']=='failed'
    return {'id':code,'category':category,'scenario':scenario,'expected':expected,'passed':bool(passed),'observed':observed,
            'ticks':len(journal),**totals,'seconds':round(time.monotonic()-started,1)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--label',default='after')
    parser.add_argument('--out',type=Path,default=REPO/'course/eval')
    args=parser.parse_args()
    results=[run_case(case) for case in CASES]
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/f'{args.label}.json').write_text(json.dumps(results,ensure_ascii=False,indent=1),encoding='utf-8')
    lines=[f'# Eval-набор: прогон «{args.label}»','',
           f"Пройдено {sum(r['passed'] for r in results)} из {len(results)}. Режим: копия проекта, заглушки инструментов.",'',
           '| Кейс | Тип | Сценарий | Ожидаемый результат | Итог | Наблюдение | Тактов | LLM | GAP |','|---|---|---|---|---|---|---|---|---|']
    for r in results:
        lines.append(f"| {r['id']} | {r['category']} | {r['scenario']} | {r['expected']} | {'✅' if r['passed'] else '❌'} | {r['observed']} | {r['ticks']} | {r['llm_calls']} | {r['gap_runs']} |")
    (args.out/f'{args.label}.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    for r in results:print(r['id'],'PASS' if r['passed'] else 'FAIL',r['observed'][:110])
    print(f"{sum(r['passed'] for r in results)}/{len(results)}")


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    main()
