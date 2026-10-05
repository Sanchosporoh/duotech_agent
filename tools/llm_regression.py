"""Regression "before / after" for a change of the LLM model or prompt, situation by situation.

The eval suite (tools/run_eval.py) runs on a rule-based LLM stub and cannot see a prompt or model change.
This script compares two answer files of tools/compare_llm.py on the same situations (course/llm_eval/cases.json)
by rules fixed in advance (RULES below, the same as in compare_llm).

Run:  python tools/llm_regression.py --before course/llm_eval/comparison.json openai/gpt-4.1 \
          --after course/llm_eval/comparison.json openai/gpt-4o-mini --out course/eval/regression_llm.md
"""
import argparse
import json
from pathlib import Path
import sys

RULES={
    'гипотезы':'ответ по схеме, нет выдуманных скважин, главная причина — первой гипотезой',
    'выбор инструмента':'ответ по схеме; выбранный инструмент показан, сам выбор не оценивается',
    'наборы':'ответ по схеме, все скважины наборов из реестра; покрытие потребности показано',
}


def passed(row):
    if row is None or row.get('error') or not row.get('valid'):return False
    if row['task']=='гипотезы':return not row.get('unknown_wells') and bool(row.get('key_well_first'))
    if row['task']=='наборы':return not row.get('outside_register')
    return True


def detail(row):
    if row is None:return 'нет ответа'
    if row.get('error'):return 'ошибка: '+str(row['error'])[:60]
    if row['task']=='гипотезы':return f"первая: {row.get('first','')[:45]}"
    if row['task']=='наборы':return f"вне реестра: {', '.join(row.get('outside_register') or []) or 'нет'}; покрытие {row.get('best_register_coverage')}"
    return row.get('tool','—')


def load(path,model):
    return {(r['task'],r['case']):r for r in json.loads(Path(path).read_text(encoding='utf-8')) if r.get('model')==model}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--before',nargs=2,metavar=('FILE','MODEL'),required=True)
    parser.add_argument('--after',nargs=2,metavar=('FILE','MODEL'),required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    before,after=load(*args.before),load(*args.after)
    lines=[f'# Регрессия LLM «до / после»: {args.before[1]} → {args.after[1]}','',
           'Ситуации — `course/llm_eval/cases.json`. Правила записаны до прогонов (`tools/compare_llm.py`):','']
    lines+=[f'- **{task}** — {rule}' for task,rule in RULES.items()]
    lines+=['','| Шаг | Ситуация | До | После | Итог |','|---|---|---|---|---|']
    counts={'регрессия':0,'улучшение':0,'без изменений':0}
    for key in sorted(set(before)|set(after),key=lambda k:(list(RULES).index(k[0]),k[1])):
        b,a=before.get(key),after.get(key)
        verdict='без изменений' if passed(b)==passed(a) else 'регрессия' if passed(b) else 'улучшение'
        counts[verdict]+=1
        mark=lambda r:('✅ ' if passed(r) else '❌ ')+detail(r)
        lines.append(f'| {key[0]} | {key[1]} | {mark(b)} | {mark(a)} | {verdict} |')
    total=lambda rows:sum(passed(r) for r in rows.values())
    lines+=['',f"До: {total(before)} из {len(before)}; после: {total(after)} из {len(after)}. "
            f"Регрессий {counts['регрессия']}, улучшений {counts['улучшение']}, без изменений {counts['без изменений']}."]
    args.out.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines))


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    main()
