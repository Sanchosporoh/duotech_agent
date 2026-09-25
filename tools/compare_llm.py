"""Compare LLMs on the same real situations (course criterion 4.3: model per step and cost).

Inputs: course/llm_eval/cases.json — contexts and Codex answers from the real Codex + PetEx run.
For each model: hypotheses (3 situations), tool choice and measure sets (3 situations).
Quality is checked by rules, cost comes from OpenRouter usage. Nothing touches PetEx.

Run (key in OPENROUTER_API_KEY, user environment is enough):
  python tools/compare_llm.py
  python tools/compare_llm.py --models openai/gpt-4o-mini z-ai/glm-5.3-flash
Results: course/llm_eval/comparison.json and course/llm_eval/comparison.md
"""
import argparse
import json
from pathlib import Path
import sys
import pandas as pd

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from src import llm_client, well_trust
from src.live_reasoning import SCHEMA as HYP_SCHEMA, hypothesis_prompt
from src.live_planning import SCHEMA as TOOL_SCHEMA, SETS_SCHEMA, TOOLS, planning_prompt

MODELS=['openai/gpt-4o-mini','openai/gpt-4.1','deepseek/deepseek-v4.1-flash','z-ai/glm-5.3-flash']


def score_hypotheses(answer,case):
    wells={row['well_id'] for row in case['context']['telemetry']}
    items=answer['hypotheses']
    unknown=sorted({w for h in items for w in h['candidate_wells']}-wells)
    return {'valid':not unknown and 4<=len(items)<=6,'count':len(items),'unknown_wells':unknown,
            'key_well_first':case['key_well'] in items[0]['candidate_wells'],
            'key_well_any':any(case['key_well'] in h['candidate_wells'] for h in items),
            'first':items[0]['title']}


def score_sets(answer,case):
    options={o['well_id']:o for o in case['payload']['opportunities']}
    need=case['payload']['preliminary_need']['required_extra_oil_tpd']
    alternatives=answer['alternatives']
    outside=sorted({w for a in alternatives for w in a['selected_wells']}-set(options))
    repeats=any(len(set(a['selected_wells']))!=len(a['selected_wells']) for a in alternatives)
    coverage=max((sum(options[w]['potential_oil_tpd'] for w in a['selected_wells'] if w in options)/need for a in alternatives),default=0)
    return {'valid':bool(alternatives) and not outside and not repeats,'sets':len(alternatives),'outside_register':outside,
            'best_register_coverage':round(coverage,2),'wells':[a['selected_wells'] for a in alternatives]}


def run_case(model,prompt,schema,key):
    try:
        answer,meta=llm_client.ask(prompt,schema,model,llm_client.OPENROUTER_URL,key)
        return answer,meta,None
    except Exception as exc:  # the comparison records failures instead of stopping
        text=str(exc)
        # A schema error starts with the whole answer; keep the reason itself.
        reason=text.split('\n',1)[0][-200:] if 'Failed validating' in text or ' is too ' in text else text[:300]
        return None,{'model':model},reason


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--models',nargs='+',default=MODELS)
    args=parser.parse_args()
    key=llm_client.api_key()
    if not key:
        print('Нет ключа OPENROUTER_API_KEY. Задайте его в PowerShell:\n'
              "  [Environment]::SetEnvironmentVariable('OPENROUTER_API_KEY','<ключ>','User')");return 1
    cases=json.loads((REPO/'course/llm_eval/cases.json').read_text(encoding='utf-8'))
    rows=[]
    for case in cases['hypotheses']:
        rows.append({'model':'codex (эталон, настоящий прогон)','task':'гипотезы','case':case['id'],'error':None,**score_hypotheses(case['codex_answer'],case)})
    for case in cases['measure_sets']:
        rows.append({'model':'codex (эталон, настоящий прогон)','task':'наборы','case':case['id'],'error':None,**score_sets(case['codex_proposal'],case)})
    for model in args.models:
        for case in cases['hypotheses']:
            telemetry=pd.DataFrame(case['context']['telemetry'])
            trust=well_trust.compute(REPO,telemetry,case['context']['hour'])
            answer,meta,error=run_case(model,hypothesis_prompt(case['context'],trust),HYP_SCHEMA,key)
            rows.append({'task':'гипотезы','case':case['id'],**meta,'error':error,**(score_hypotheses(answer,case) if answer else {'valid':False})})
            print(model,case['id'],'ok' if answer else error,flush=True)
        for case in cases['measure_sets']:
            payload=dict(case['payload'],tools=TOOLS)
            answer,meta,error=run_case(model,planning_prompt(payload),TOOL_SCHEMA,key)
            rows.append({'task':'выбор инструмента','case':case['id'],**meta,'error':error,'valid':answer is not None,
                         'tool':answer and answer['tool'],'tool_reason':answer and answer['tool_reason']})
            answer,meta,error=run_case(model,planning_prompt(payload,sets_only=True),SETS_SCHEMA,key)
            rows.append({'task':'наборы','case':case['id'],**meta,'error':error,**(score_sets(answer,case) if answer else {'valid':False})})
            print(model,case['id'],'ok' if answer else error,flush=True)
    out=REPO/'course/llm_eval'
    (out/'comparison.json').write_text(json.dumps(rows,ensure_ascii=False,indent=1),encoding='utf-8')
    (out/'comparison.md').write_text(summary(rows),encoding='utf-8')
    print(summary(rows))
    return 0


def summary(rows):
    frame=pd.DataFrame(rows)
    lines=['| Модель | Корректные ответы | Главная причина первой гипотезой | Наборы в реестре, покрытие потребности (max) | Скрининг выбран | Токены вход/выход | Стоимость, $ | Время ответа, с |',
           '|---|---|---|---|---|---|---|---|']
    for model,part in frame.groupby('model',sort=False):
        hyp=part[part.task=='гипотезы'];sets=part[part.task=='наборы'];tool=part[part.task=='выбор инструмента']
        tokens='—' if 'prompt_tokens' not in part or part.prompt_tokens.isna().all() else f"{int(part.prompt_tokens.fillna(0).sum())}/{int(part.completion_tokens.fillna(0).sum())}"
        cost='—' if 'cost_usd' not in part or part.cost_usd.isna().all() else f"{part.cost_usd.fillna(0).sum():.4f}"
        seconds='—' if 'seconds' not in part or part.seconds.isna().all() else f"{part.seconds.mean():.1f}"
        coverage='—' if 'best_register_coverage' not in sets or sets.best_register_coverage.isna().all() else f"{sets.best_register_coverage.mean():.2f}"
        screen='—' if tool.empty else f"{(tool.tool=='screen_single_wells').sum()} из {len(tool)}"
        key_first=f"{int(hyp.key_well_first.fillna(False).sum())} из {len(hyp)}" if 'key_well_first' in hyp else '—'
        lines.append(f"| {model} | {int(part.valid.fillna(False).sum())} из {len(part)} | {key_first} | {int(sets.valid.fillna(False).sum())} из {len(sets)}, {coverage} | {screen} | {tokens} | {cost} | {seconds} |")
    return '\n'.join(lines)+'\n'


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
