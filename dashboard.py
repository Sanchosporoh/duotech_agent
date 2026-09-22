from datetime import datetime
from pathlib import Path
import importlib
import json
import os
import subprocess
import sys
import pandas as pd
import streamlit as st
import altair as alt
from src import day_case, incident_view, incident_lifecycle, potential_register, prosper_diagnostics

day_case, incident_view, incident_lifecycle = importlib.reload(day_case), importlib.reload(incident_view), importlib.reload(incident_lifecycle)
ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Мониторинг добычи", layout="wide")
st.markdown("""<style>header[data-testid="stHeader"],div[data-testid="stToolbar"],div[data-testid="stDecoration"]{display:none}.block-container{padding-top:.2rem;padding-bottom:.7rem;max-width:1700px}h1,h2,h3,h4{margin:.15rem 0 .3rem}div[data-testid="stMetric"]{background:#f4f6f8;padding:.35rem .6rem;border-radius:.45rem}div[data-testid="stVerticalBlock"]{gap:.35rem}.readable-table{overflow:auto;max-height:520px;border:1px solid #d8dee8;border-radius:.45rem}.readable-table table{width:100%;border-collapse:collapse;font-size:.86rem}.readable-table th{position:sticky;top:0;background:#edf1f7;color:#1f2937;z-index:1;text-align:left}.readable-table th,.readable-table td{padding:.45rem .55rem;border-bottom:1px solid #d8dee8;vertical-align:top;white-space:normal;overflow-wrap:anywhere;min-width:7rem}.readable-table td:last-child{min-width:20rem}</style>""", unsafe_allow_html=True)
if "simulation_hour" not in st.session_state: st.session_state.simulation_hour = 0
if "approvals" not in st.session_state: st.session_state.approvals = {}
for module_name in ('live_monitor','live_reasoning','live_checks','license_retry','live_adaptation','live_planning','restoration_forecast','restoration_planning','proposal_selection','live_execution','autonomous_cycle','live_dashboard'):
    importlib.reload(importlib.import_module('src.'+module_name))
importlib.import_module('src.live_dashboard').render(ROOT)
st.stop()

def time_chart(frame, columns, y_title, height=220):
    """Time chart with a local Y range and 24-hour clock labels."""
    source=(frame.reset_index().melt(id_vars="timestamp",value_vars=columns,
                                    var_name="Показатель",value_name="Значение").dropna())
    values=source["Значение"].astype(float)
    low,high=float(values.min()),float(values.max())
    span=max(high-low,abs(high)*.015,1.0)
    domain=[low-span*.18,high+span*.18] if not source.empty else [0,1]
    return (alt.Chart(source).mark_line(point=True).encode(
        x=alt.X("timestamp:T",title=None,axis=alt.Axis(format="%H:%M",labelAngle=0,tickCount="hour")),
        y=alt.Y("Значение:Q",title=y_title,scale=alt.Scale(domain=domain,zero=False)),
        color=alt.Color("Показатель:N",title=None),
        tooltip=[alt.Tooltip("timestamp:T",title="Время",format="%H:%M"),
                 alt.Tooltip("Показатель:N"),alt.Tooltip("Значение:Q",format=".2f")]
    ).properties(height=height).interactive(bind_y=False))

def production_chart(frame, height=225):
    source=frame[["timestamp","plan_oil_tpd","separator_oil_tpd"]].copy()
    source["Нижняя граница −5%"] = source["plan_oil_tpd"]*.95
    source["Верхняя граница +5%"] = source["plan_oil_tpd"]*1.05
    actual=source.melt(id_vars="timestamp",value_vars=["plan_oil_tpd","separator_oil_tpd"],
                       var_name="Показатель",value_name="Значение")
    limits=source.melt(id_vars="timestamp",value_vars=["Нижняя граница −5%","Верхняя граница +5%"],
                       var_name="Показатель",value_name="Значение")
    all_values=pd.concat([actual,limits],ignore_index=True)["Значение"].astype(float)
    low,high=float(all_values.min()),float(all_values.max()); pad=max((high-low)*.05,1.0)
    x=alt.X("timestamp:T",title=None,axis=alt.Axis(format="%H:%M",labelAngle=0,tickCount="hour"))
    solid=alt.Chart(actual).mark_line(point=True).encode(
        x=x,y=alt.Y("Значение:Q",title="нефть, т/сут",scale=alt.Scale(domain=[low-pad,high+pad],zero=False)),
        color=alt.Color("Показатель:N",title=None),
        tooltip=[alt.Tooltip("timestamp:T",title="Время",format="%H:%M"),alt.Tooltip("Показатель:N"),alt.Tooltip("Значение:Q",format=".2f")])
    dashed=alt.Chart(limits).mark_line(strokeDash=[7,5],strokeWidth=2).encode(
        x=x,y=alt.Y("Значение:Q",scale=alt.Scale(domain=[low-pad,high+pad],zero=False)),
        color=alt.Color("Показатель:N",title=None,scale=alt.Scale(range=["#d97706","#d97706"])),
        tooltip=[alt.Tooltip("timestamp:T",title="Время",format="%H:%M"),alt.Tooltip("Показатель:N"),alt.Tooltip("Значение:Q",format=".2f")])
    return (solid+dashed).properties(height=height).interactive(bind_y=False)

head, ctl = st.columns([5,2])
head.markdown("## Почасовой мониторинг → диагностика → решение")
with ctl:
    a,b,c,d=st.columns(4)
    if a.button("−1 час",disabled=st.session_state.simulation_hour==0): st.session_state.simulation_hour-=1; st.rerun()
    if b.button("＋1 час",type="primary",disabled=st.session_state.simulation_hour==23): st.session_state.simulation_hour+=1; st.rerun()
    if c.button("Сброс"): st.session_state.simulation_hour=0; st.session_state.approvals={}; st.rerun()
    if d.button("Открыть GAP"):
        os.startfile(ROOT/"runtime"/"petex_case"/"IM_2022_06"/"BEL_PROD.gap")

hour=st.session_state.simulation_hour
wells,_=day_case.build_hourly_case(ROOT)
wells=day_case.apply_approved_actions(wells,st.session_state.approvals)
separator=incident_view.separator_history(wells)
telemetry=incident_view.sparse_telemetry(wells)
incidents=incident_view.opened_incidents(separator,hour)
for i in incidents.index:
    rec=st.session_state.approvals.get(incidents.at[i,"incident_id"],{})
    if isinstance(rec,dict) and rec.get("status"):
        status=rec["status"]
        elapsed=hour-int(rec.get("hour",hour))
        if status=="Утверждено" and incidents.at[i,"incident_id"]=="INC-002":
            if elapsed<2: status="Утверждено · бригада в пути"
            elif elapsed<4: status="В работе · диагностика/перезапуск"
            else: status="Выполнено · эффект получен"
        elif status=="Утверждено" and incidents.at[i,"incident_id"]=="INC-001":
            status="Утверждено · эффект со следующего часа" if elapsed<1 else "Выполнено · режимы применены"
        incidents.at[i,"status"]=status
now=separator[separator.hour<=hour]; last=now.iloc[-1]
fact=None if pd.isna(last.separator_oil_tpd) else float(last.separator_oil_tpd)
loss=((now.plan_oil_tpd-now.separator_oil_tpd).clip(lower=0)/24).sum()
m=st.columns(5)
m[0].metric("Расчётный час",f"{hour:02d}:00"); m[1].metric("План объекта",f"{last.plan_oil_tpd:.1f} т/сут")
m[2].metric("Сепаратор","нет факта" if fact is None else f"{fact:.1f} т/сут",None if fact is None else f"{fact-last.plan_oil_tpd:+.1f}")
m[3].metric("Накопленный недобор",f"{loss:.2f} т"); m[4].metric("Открыто инцидентов",len(incidents))

left,right=st.columns([1.35,1])
with left: st.altair_chart(production_chart(now,225),use_container_width=True)
with right:
    st.markdown("#### Журнал инцидентов")
    current_deviation=(float(last.separator_oil_tpd)-float(last.plan_oil_tpd))/float(last.plan_oil_tpd)*100
    if incidents.empty and current_deviation<=-2:
        st.warning(f"Раннее предупреждение: отклонение {current_deviation:.2f}%. Допуск −5% ещё не пересечён.")
    elif incidents.empty: st.success("Отклонений за допуском пока нет. Агент продолжает контроль.")
    else:
        show=incidents.rename(columns={"incident_id":"Инцидент","opened_hour":"Час","signal":"Сигнал сепаратора","observed_loss_tpd":"Потеря, т/сут","status":"Статус"})
        st.dataframe(show[["Инцидент","Час","Сигнал сепаратора","Потеря, т/сут","Статус"]],hide_index=True,use_container_width=True,height=195)
if incidents.empty:
    st.info("Подтверждённых инцидентов нет. Диагностика запустится автоматически при выходе отклонения за допуск."); st.stop()

ids=incidents.incident_id.tolist()
selected_id=st.selectbox("Разобрать инцидент",ids,index=len(ids)-1)
incident=incidents[incidents.incident_id==selected_id].iloc[0]
hyp=incident_view.ranked_hypotheses(ROOT,selected_id); best=hyp.iloc[0]
lifecycle_path=ROOT/"data"/"incident_lifecycle.json"
lifecycle=incident_lifecycle.ensure_incident(lifecycle_path,selected_id,str(best.hypothesis))
current_version=lifecycle["versions"][-1]
st.markdown(f"### {selected_id}: от сигнала сепаратора до решения")
st.caption("Скважина не известна заранее. Гипотезы сопоставляются с доступными признаками и сценарными расчётами, после чего выбирается рабочая версия причины.")
stage_titles={"awaiting_human_decision":"Ожидает решения инженера","awaiting_revision_calculation":"Требуется пересчёт новой версии",
              "approved_for_execution":"Утверждено к исполнению","closed_rejected":"Закрыто без исполнения"}
flow=st.columns(5)
flow[0].metric("1. Сигнал","получен")
flow[1].metric("2. Гипотезы","ранжированы")
flow[2].metric("3. Рабочая гипотеза",str(best.well_id))
flow[3].metric("4. Версия решения",f"№ {current_version['version']}")
flow[4].metric("5. Состояние",stage_titles.get(lifecycle["stage"],lifecycle["stage"]))
t1,t2,t3,t4,t5=st.tabs(["1 · Наблюдение","2 · Гипотезы и ИМА","3 · Телеметрия","4 · Решение и HITL","5 · Реестр возможностей"])
with t1:
    x=st.columns(3); x[0].metric("Измеренная потеря",f"{incident.observed_loss_tpd:.2f} т/сут"); x[1].metric("Кандидат для проверки",best.well_id); x[2].metric("Причина","не подтверждена")
    st.write("Сепаратор показывает снижение объекта. Почасовых дебитов скважин нет: используются редкие сигналы и сценарные расчёты.")
with t2:
    codex_file=ROOT/"data"/f"codex_hypotheses_{selected_id}.json"
    if codex_file.exists():
        codex_result=json.loads(codex_file.read_text(encoding="utf-8"))
        st.markdown("#### Шаг 2.1 · Гипотезы сформированы Codex CLI")
        st.write(codex_result["assessment"])
        llm_rows=[]
        for n,item in enumerate(codex_result["hypotheses"],1):
            llm_rows.append({"№":n,"Гипотеза Codex":item["title"],
                             "Кандидаты":", ".join(item["candidate_wells"]),
                             "Инженерное обоснование":item["engineering_rationale"],
                             "Как проверить":item["verification"],
                             "Чего не хватает":"; ".join(item["missing_data"])})
        st.dataframe(pd.DataFrame(llm_rows),hide_index=True,use_container_width=True,height=245)
        st.caption("Codex предлагает направления проверки, но не подтверждает причину и не рассчитывает эффект.")
    else:
        st.warning("Гипотезы Codex для этого инцидента ещё не сформированы.")
    st.markdown("#### Шаг 2.2 · Признаки и фактически выполненные проверки")
    display=hyp.rename(columns={"rank":"Приоритет проверки","hypothesis":"Гипотеза","well_id":"Скважина","predicted_loss_tpd":"Потеря GAP при полном отключении, т/сут","mismatch_tpd":"Невязка баланса, т/сут","evidence":"Основание","check_source":"Источник проверки","missing_data":"Чего не хватает"})
    st.dataframe(display,hide_index=True,use_container_width=True,height=260)
    if selected_id=="INC-001":
        st.warning("W27 выделена по телеметрии. Ниже сопоставлены прежний приток и лифт по рассчитанным кривым. Причина не подтверждена: ещё нужна проверка группового баланса. Порядок строк — приоритет проверки, не вероятность причины.")
        audit, probe = prosper_diagnostics.load_probe(ROOT)
        if audit:
            observed=telemetry[(telemetry.well_id=='W_BEL_27_TLBB') & (telemetry.hour<=hour)].iloc[-1]
            st.markdown("#### Текущий инцидент · прежний приток против прежнего лифта")
            st.write(f"Давление приёма сейчас: {observed.sensor_pressure_bar:.2f} бар абс.; частота {observed.frequency_hz:.0f} Гц.")
            try:
                pressure_tolerance=json.loads((ROOT/'config'/'diagnostic_sensors.json').read_text(encoding='utf-8'))['W_BEL_27_TLBB']['pressure_residual_tolerance_bar']
                checks=prosper_diagnostics.diagnose_intake(audit,float(observed.sensor_pressure_bar),pressure_tolerance)
                check_rows=[]
                for name,check in checks.items():
                    check_rows.append({'Зависимость':name,'Статус':check['status'],'Дебит жидкости, м³/сут':check.get('rate_m3d'),'Нижняя оценка':check.get('min_m3d'),'Верхняя оценка':check.get('max_m3d')})
                st.dataframe(pd.DataFrame(check_rows).round(2),hide_index=True,use_container_width=True)
                st.caption("Это две оценки по прежней модели, не индивидуальный замер. Учитывается ±1,5 бар; полная неопределённость модели ещё не оценена. Приток приведён к приёму через рассчитанный нижний участок. Несогласованность оценок поддерживает изменение притока/лифта, но локализацию нужно проверять групповым балансом.")
            except (ValueError,KeyError) as exc:
                st.warning(str(exc))
            with st.expander("W27 · Выполненный пробный расчёт лифта", expanded=True):
                latest = audit.get("latest_test_by_date", {})
                params = audit["parameters"]
                st.caption(f"Последний замер в файле: {latest.get('Date', 'нет даты')}. Частота модели: {float(params['pump_frequency']['value']):.0f} Гц. Износ: {float(params['pump_wear']['value']):.3f}, без подгонки.")
                boundary = audit.get("lift_probe", {}).get("boundary_conditions", {})
                if boundary:
                    st.write(f"Буферное давление {boundary['whp_psig'] * .0689475729:.2f} бар изб.; обводнённость {boundary['wc_pct']:.1f}%; газовый фактор {boundary['gor_scf_stb'] * .178107607:.2f} м³/м³.")
                if not probe.empty:
                    st.dataframe(probe.round(2), hide_index=True, use_container_width=True)
                reference = audit.get("lift_probe", {}).get("gauge_reference")
                if reference:
                    st.write(f"Датчик: глубина {reference['depth_ft'] * .3048:.2f} м; замер {reference['measured_pressure_psig'] * .0689475729:.2f} бар изб. Насос: {reference['pump_depth_ft'] * .3048:.2f} м.")
                    neighbours = audit['lift_probe']['points'][0].get('gauge_neighbours', []) if audit['lift_probe']['points'] else []
                    if neighbours:
                        around = pd.DataFrame(neighbours)
                        around['Глубина, м'] = around.depth_ft * .3048
                        around['Давление, бар изб.'] = around.pressure_psig * .0689475729
                        st.dataframe(around[['Глубина, м', 'Давление, бар изб.']].round(2), hide_index=True, use_container_width=True)
                    try:
                        intake_table, comparison = prosper_diagnostics.baseline_comparison(ROOT, audit)
                        st.caption("Положение датчика подтверждено инженером: приём насоса. Точка выбирается по скачку профиля, а не по совпадению с замером.")
                        st.dataframe(intake_table.round(2), hide_index=True, use_container_width=True)
                        st.write(f"Исходный режим: замер {comparison['measured_bar']:.2f}, расчёт {comparison['calculated_bar']:.2f} бар изб.; невязка «замер − расчёт» {comparison['residual_bar']:+.2f} бар.")
                        verdict = "в допуске" if comparison['within_tolerance'] else "вне допуска"
                        st.write(f"Допуск ±{comparison['tolerance_bar']:.1f} бар: исходный режим {verdict}.")
                        st.caption("Это соответствие последнему исходному замеру, не проверка текущего инцидента. Допуск давления не подтверждает причину снижения добычи.")
                    except (ValueError, KeyError, OSError) as exc:
                        st.error(f"Сравнение давления приёма недоступно: {exc}")
                if audit.get("lift_probe", {}).get("error"):
                    st.error(audit['lift_probe']['error'])
                st.info("Это чувствительность лифта к заданному дебиту при прежнем состоянии насоса, а не подбор причины. Давление рассчитано до конца профиля; давление датчика нельзя сравнивать с ним без приведения к одной глубине. Для диагностики нужны текущая оценка дебита и давления, проверка IPR и сравнение на одинаковой глубине.")
    else:
        st.info("GAP рассчитан для узкой гипотезы полного отключения одной скважины. Совпадение потери с сепаратором само по себе не определяет виновную скважину.")
with t3:
    candidates=[x for x in hyp.well_id.unique() if x!="—"]
    well=st.selectbox("Скважина для проверки сигналов",candidates)
    tel=telemetry[(telemetry.well_id==well)&(telemetry.hour<=hour)].copy()
    x,y=st.columns(2)
    if tel.frequency_hz.notna().any():
        x.altair_chart(time_chart(tel[["timestamp","frequency_hz"]],["frequency_hz"],"Гц",205),use_container_width=True)
    else:
        x.info("Частота ЭЦН для этой скважины недоступна или неприменима.")
    y.altair_chart(time_chart(tel[["timestamp","sensor_pressure_bar","fbhp_bara"]],["sensor_pressure_bar","fbhp_bara"],"бар абс.",205),use_container_width=True)
    tab=tel.tail(6).rename(columns={"timestamp":"Время","frequency_hz":"Частота, Гц","sensor_pressure_bar":"Давление датчика, бар","fbhp_bara":"Забойное давление, бар","esp_current_a":"Ток, А","vibration_mm_s":"Вибрация, мм/с","signal":"Сигнал"})
    st.dataframe(tab[["Время","Частота, Гц","Давление датчика, бар","Забойное давление, бар","Ток, А","Вибрация, мм/с","Сигнал"]],hide_index=True,use_container_width=True)
    st.caption("Разрывы намеренные: это последние доступные сигналы, а не выдуманный почасовой дебит.")
with t4:
    st.markdown(f"#### Версия решения №{current_version['version']}")
    if lifecycle["stage"]=="awaiting_revision_calculation":
        st.warning(f"Новая постановка создана по комментарию инженера: {current_version['human_comment']}. Стратегия должна быть пересобрана и повторно рассчитана в GAP.")
        if selected_id!="INC-002":
            st.info("Автоматический обработчик доработки пока подключён к кейсу остановки скважины INC-002.")
        elif st.button("Запустить доработку: Codex → GAP",type="primary"):
            with st.spinner("Codex пересобирает стратегии, затем GAP последовательно рассчитывает три варианта..."):
                completed=subprocess.run([sys.executable,str(ROOT/"tools"/"process_revision.py"),"--incident",selected_id],
                    cwd=ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace",check=False)
            if completed.returncode==0:
                st.success("Новая версия рассчитана и готова к повторному рассмотрению.")
                st.rerun()
            else:
                st.error("Доработка остановлена. Предыдущая версия сохранена.\n\n"+(completed.stderr or completed.stdout)[-2000:])
    selected_strategy=None
    approval_allowed=True
    if selected_id=="INC-001":
        actions=day_case.compensation_table(wells)
        st.warning("Для первого инцидента показан прежний демонстрационный набор режимов. Диагностическая доадаптация IPR/насоса не выполнена; этот набор не является результатом подтверждения причины в ИМА.")
        approval_allowed=False
    else:
        strategy_results=[]
        strategy_names={"technological":"Технологическая","geological":"Геологическая","balanced":"Сбалансированная"}
        revision_files=current_version.get("result_files",{})
        for strategy_id,title in strategy_names.items():
            if strategy_id in revision_files:
                path=Path(revision_files[strategy_id])
            elif current_version["version"]==1:
                path=ROOT/"data"/f"gap_optimization_result_{strategy_id}.json"
            else:
                continue
            if path.exists():
                payload=json.loads(path.read_text(encoding="utf-8")); summary=payload["summary"]
                strategy_results.append({"id":strategy_id,"Стратегия":title,
                    "Управляемых объектов":len(payload["configured_controls"]),
                    "Компенсация при остановке, т/сут":round(summary["optimisation_gain_sm3d"]*day_case.OIL_DENSITY_T_M3,2),
                    "Баланс к 24:00, т":round(summary["horizon_balance_t"],2),
                    "Мин. Pзаб, бар":round(summary["minimum_fbhp_bar"],2),
                    "Вода в ограничении":"да" if summary["water_limit_met"] else "нет",
                    "Цель к 24:00":"достигнута" if summary["target_met_by_horizon_end"] else "не достигнута",
                    "payload":payload})
        if strategy_results:
            st.markdown("#### Сравнение стратегий по расчёту GAP")
            st.dataframe(pd.DataFrame([{k:v for k,v in row.items() if k not in {"id","payload"}} for row in strategy_results]),hide_index=True,use_container_width=True,height=155)
            successful=[row for row in strategy_results if row["payload"]["summary"]["target_met_by_horizon_end"]]
            calculated_choice=current_version.get("strategy")
            available_ids=[row["id"] for row in strategy_results]
            default_id=calculated_choice if calculated_choice in available_ids else (successful[0]["id"] if successful else strategy_results[0]["id"])
            selected_strategy=st.selectbox("Стратегия для рассмотрения",[row["id"] for row in strategy_results],
                index=[row["id"] for row in strategy_results].index(default_id),
                format_func=lambda value: strategy_names[value])
            chosen=next(row["payload"] for row in strategy_results if row["id"]==selected_strategy)
            outage={row["well_id"]:row for row in chosen["optimised"]["wells"]}
            restored={row["well_id"]:row for row in chosen["restored_optimised"]["wells"]}
            action_rows=[]
            for control in chosen["configured_controls"]:
                wid=control["well_id"]; before=float(control["current"])
                during=outage.get(wid,{}).get("control_optimised")
                after=restored.get(wid,{}).get("control_optimised")
                if during is None and after is None: continue
                action_rows.append({"Скважина":wid,"Тип":control["well_type"].replace("OilProducer", ""),
                    "Исходный контроль":round(before,2),
                    "При остановке W22":None if during is None else round(float(during),2),
                    "После восстановления":None if after is None else round(float(after),2),
                    "Допустимый диапазон":f"{control['minimum']:.1f}–{control['maximum']:.1f}"})
            actions=pd.DataFrame(action_rows)
            st.dataframe(actions,hide_index=True,use_container_width=True,height=220)
            summary=chosen["summary"]
            approval_allowed=bool(summary["target_met_by_horizon_end"] and summary["water_limit_met"] and summary["minimum_fbhp_bar"]>=79.99)
            x=st.columns(3); x[0].metric("Баланс к 24:00",f"{summary['horizon_balance_t']:+.2f} т"); x[1].metric("Вода","ограничение соблюдено" if summary["water_limit_met"] else "нарушено"); x[2].metric("Минимальный Pзаб",f"{summary['minimum_fbhp_bar']:.2f} бар")
            if summary["target_met_by_horizon_end"]: st.success("Стратегия закрывает накопленный недобор к 24:00 по расчёту GAP.")
            else: st.error("Стратегия не закрывает накопленный недобор. Утверждение недоступно — требуется следующая итерация.")
        else:
            actions=pd.DataFrame()
            st.warning("Результаты стратегий GAP ещё не рассчитаны.")
    if selected_id=="INC-001":
        st.dataframe(actions,hide_index=True,use_container_width=True,height=175)
        water=float(pd.read_csv(ROOT/"data"/"petex_baseline.csv").eval("liquid_rate-oil_rate").sum())
        x=st.columns(3); x[0].metric("Расчётный эффект",f"+{actions['Прирост, т/сут'].sum():.2f} т/сут"); x[1].metric("Вода",f"≤ {water:.2f} м³/сут"); x[2].metric("Минимальный FBHP","≥ 80 бар")
    current=st.session_state.approvals.get(selected_id,{})
    if isinstance(current,dict) and current.get("status"):
        message=f"Текущее решение: {current['status']}"
        if selected_id=="INC-002" and current.get("status")=="Утверждено":
            elapsed=max(0,hour-int(current["hour"]))
            if elapsed<2: message+=f" · мобилизация бригады ({elapsed}/2 ч)"
            elif elapsed<4: message+=f" · диагностика и перезапуск ({elapsed-2}/2 ч)"
            else: message+=" · работа завершена, эффект учтён"
        st.info(message)
    with st.form(f"approval_{selected_id}"):
        decision=st.radio("Решение инженера",["Утвердить","Вернуть на доработку","Отклонить"],horizontal=True)
        comment=st.text_input("Комментарий / новое ограничение")
        invalid_revision=(decision=="Вернуть на доработку" and not comment.strip())
        calculation_pending=lifecycle["stage"]=="awaiting_revision_calculation"
        submitted=st.form_submit_button("Зафиксировать",type="primary")
        st.caption("Для возврата на доработку укажите, что изменить. Доступность утверждения проверяется при отправке.")
        if calculation_pending: st.caption("Новая версия ожидает расчёта. Можно отклонить её; утверждение и повторный возврат пока недоступны.")
    if submitted:
        if invalid_revision:
            st.error("Решение не сохранено: для доработки нужен комментарий.")
            submitted=False
        elif calculation_pending and decision!="Отклонить":
            st.error("Решение не сохранено: сначала необходимо рассчитать созданную версию.")
            submitted=False
        elif decision=="Утвердить" and not approval_allowed:
            st.error("Утверждение не сохранено: нет допустимого рассчитанного решения. Можно вернуть предложение на доработку с комментарием или отклонить.")
            submitted=False
    if submitted:
        status={"Утвердить":"Утверждено","Вернуть на доработку":"На доработке","Отклонить":"Отклонено"}[decision]
        st.session_state.approvals[selected_id]={"status":status,"hour":hour,"comment":comment,"strategy":selected_strategy}
        gap_text="—"
        if selected_id=="INC-002" and 'summary' in locals(): gap_text=f"Баланс к 24:00 {summary['horizon_balance_t']:+.2f} т"
        lifecycle=incident_lifecycle.record_decision(lifecycle_path,selected_id,status,comment,selected_strategy,gap_text)
        log=ROOT/"data"/"approval_log.csv"
        pd.DataFrame([{"recorded_at":datetime.now().isoformat(timespec="seconds"),"simulation_hour":hour,"incident_id":selected_id,"decision":status,"comment":comment}]).to_csv(log,mode="a",header=not log.exists(),index=False,encoding="utf-8-sig")
        st.rerun()
    st.markdown("#### История версий и решений")
    st.dataframe(pd.DataFrame(incident_lifecycle.version_rows(lifecycle)),hide_index=True,use_container_width=True,height=170)
with t5:
    st.write("Реестр потенциалов объекта. Это доступные возможности, а не выбранный план или готовые частоты. GAP рассчитывает точные режимы только выбранного набора.")
    register=potential_register.table(ROOT)
    st.metric("Сумма положительных оценок потенциала",f"{register['Оценка потенциала нефти, т/сут'].clip(lower=0).sum():.1f} т/сут")
    st.caption("Сумма индивидуальных потенциалов не гарантирует их совместную достижимость и может превышать требуемую компенсацию. Отрицательные значения — потери при защитном регулировании.")
    st.dataframe(register,hide_index=True,use_container_width=True,height=350)
    attack_file=ROOT/"data"/"cost_attack_scenario_result.json"
    if attack_file.exists():
        attack=json.loads(attack_file.read_text(encoding="utf-8"))
        with st.expander("Защита от зацикливания и лишних расчётов",expanded=False):
            st.warning("Показанные численные лимиты — черновой профиль только для текущей малой модели. Для моделей другого масштаба они неприменимы и не являются целевыми нормативами.")
            st.write("Агент останавливает итерации по общему времени, числу шагов, вызовов Codex, расчётов GAP, повтору стратегии или отсутствию заметного улучшения.")
            a,b,c,d=st.columns(4)
            a.metric("Результат теста","цикл остановлен")
            b.metric("Причина",attack["stop_reason"])
            c.metric("Вызовы Codex",attack["counters"]["llm_calls"])
            d.metric("Расчёты GAP",attack["counters"]["gap_runs"])
            st.dataframe(pd.DataFrame(attack["events"]),hide_index=True,use_container_width=True)
            labels={"max_iterations":"Итераций на инцидент","max_llm_calls":"Вызовов Codex",
                    "max_gap_runs":"Полных запусков GAP","incident_timeout_seconds":"Весь цикл, с",
                    "llm_timeout_seconds":"Один вызов Codex, с","gap_timeout_seconds":"Одно состояние GAP, с",
                    "minimum_improvement_t":"Мин. улучшение, т","max_no_progress_iterations":"Шагов без прогресса"}
            rationale=attack["limits"].get("rationale",{})
            limit_rows=[{"Ограничение":labels[key],"Значение":value,"Обоснование":rationale.get(key,"")}
                        for key,value in attack["limits"].items() if key in labels]
            st.markdown("#### Почему выбраны эти лимиты")
            st.dataframe(pd.DataFrame(limit_rows),hide_index=True,use_container_width=True,height=285)
