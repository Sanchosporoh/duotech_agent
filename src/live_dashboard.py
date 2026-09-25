"""Editable measurement-driven dashboard; prepared cases are only input fixtures."""
from datetime import datetime
import json
import pandas as pd
import streamlit as st
import altair as alt
from src import incident_view, incident_lifecycle, live_monitor, potential_register, live_reasoning, live_checks
from src import autonomous_cycle, cycle_service, escalation, live_execution, license_retry, tool_gateway, well_trust, live_planning
from src import measurement_overview
from src.calculation_dependencies import fingerprints
import importlib
measurement_overview=importlib.reload(measurement_overview)
import time
import html


def russian_text(value):
    return str(value).replace('opportunities','реестра возможностей').replace('maximum_change','максимальное допустимое изменение').replace('model control unit','единица управления модели')


def readable_table(frame):
    frame=pd.DataFrame(frame).copy()
    if frame.empty:
        st.caption('Нет данных для отображения.')
        return
    def cell(value):
        if isinstance(value,list):value='; '.join(map(str,value))
        if isinstance(value,dict):value='; '.join(f'{k}: {v}' for k,v in value.items())
        if pd.isna(value):return '—'
        return html.escape(russian_text(value))
    headings=''.join(f'<th>{html.escape(str(c))}</th>' for c in frame.columns)
    rows=''.join('<tr>'+''.join(f'<td>{cell(v)}</td>' for v in row)+'</tr>' for row in frame.itertuples(index=False,name=None))
    st.markdown('<div class="readable-table"><table><thead><tr>'+headings+'</tr></thead><tbody>'+rows+'</tbody></table></div>',unsafe_allow_html=True)


@st.fragment(run_every='15s')
def license_status(root):
    waiting=license_retry.state(root)
    if waiting.get('stage')=='waiting_license':
        seconds=max(0,int(waiting['retry_at_epoch']-time.time()))
        st.warning(f"Ожидание лицензии OpenServer. Повторная попытка через {seconds} с; временный отказ №{waiting['failure_count']}. Расчёт не выполнен.")
        if time.time()>=waiting['retry_at_epoch'] and st.session_state.get('last_license_retry')!=waiting['retry_at_epoch']:
            st.session_state.last_license_retry=waiting['retry_at_epoch']
            st.rerun()


@st.fragment(run_every='3s')
def agent_watch(root,seen):
    # The agent runs in its own process; refresh the page after each of its steps.
    if (cycle_service.clock(root).get('updated_at'),cycle_service.progress(root).get('updated_at'))!=seen:st.rerun()


STAGE_LABELS={'pending':'Агент ещё не обработал текущие данные','needs_data':'Недостаточно данных для расчёта',
    'waiting_license':'Ожидание лицензии OpenServer','waiting_petex':'PetEx занят другим расчётом — повтор в следующем такте',
    'running':'Расчёт выполняется','needs_attention':'Работа остановлена — причина указана ниже',
    'awaiting_human_decision':'Предложение готово, требуется решение инженера','awaiting_model_state':'Недостаточно данных для расчёта сети',
    'conditional_network_calculated':'Сеть рассчитана, допустимого варианта нет','approved_for_execution':'Решение утверждено'}


def check_table(rows):
    frame=pd.DataFrame(rows)
    if 'Инструмент' in frame:
        frame['Инструмент']=frame['Инструмент'].replace({
            'Прежний лифт':'Оценка по исходной кривой лифта (интерполяция, не новый расчёт)',
            'Прежний приток':'Оценка по исходной IPR (интерполяция, не подтверждение причины)',
            'Управляющий режим':'Сравнение текущей и исходной частоты',
            'Совместимость условий':'Проверка применимости исходных кривых к текущим условиям'})
        frame=frame.rename(columns={'Инструмент':'Что проверили','Статус':'Надёжность вывода'})
    return frame


def render(root):
    folder=root/'data'/'live'
    folder.mkdir(parents=True,exist_ok=True)
    sep_path=folder/'separator.csv'; tel_path=folder/'telemetry.csv'
    if not sep_path.exists() or not tel_path.exists():
        st.info('Создайте начальный набор измерений. Далее система читает только CSV; изменения не перегенерируются.')
        if st.button('Создать начальные измерения'):
            incident_view.write_initial_measurements(root,folder)
            st.rerun()
        return
    separator,telemetry,errors=cycle_service.load_measurements(root)
    if errors:
        for error in errors:st.error(error)
        return
    st.markdown('## Мониторинг по входным измерениям')
    with st.expander('Как сейчас работает система',expanded=False):
        st.write('Агент работает отдельным процессом (tools/run_agent.py) по расписанию: каждый такт — новый час измерений. Витрина только показывает записанное агентом и принимает решение инженера. Утверждение записывается в локальный реестр; эффект появляется со следующего часа с учётом фаз работ. Возврат с комментарием учитывается в следующем цикле агента.')
    agent=cycle_service.clock(root)
    step=cycle_service.progress(root)
    agent_watch(root,(agent.get('updated_at'),step.get('updated_at')))
    hour=agent.get('hour')
    a,b,c=st.columns([2,1,4])
    if a.button('Обработать следующий час сейчас',disabled=hour is not None and hour>=cycle_service.LAST_HOUR or agent.get('mode')=='wall'):
        with st.spinner('Агент обрабатывает измерения...'):cycle_service.tick(root)
        st.rerun()
    if b.button('Начать сутки заново',disabled=hour is None):cycle_service.reset_clock(root);st.rerun()
    if hour is None:
        c.write('Агент ещё не обработал ни одного часа.')
        return
    c.write(f"Час агента: {hour:02d}:00 · режим часов: {'реальное время' if agent.get('mode')=='wall' else 'ускоренная имитация'}")
    if step and not step.get('done') and step.get('hour')==hour:
        st.info('Агент работает: '+step['step'])
    license_status(root)
    if tool_gateway.backend()=='stub':
        st.warning('Режим заглушек: Codex, PROSPER и GAP не запускаются. Результаты проверяют цепочку и не являются расчётом.')
    errors=live_monitor.validate_inputs(separator,telemetry)
    if errors:
        for error in errors: st.error(error)
    else:
        visible=separator[separator.hour<=hour].sort_values('hour')
        if not visible.empty:
            chart=visible[['timestamp','plan_oil_tpd','separator_oil_tpd']].copy()
            chart['Допуск −5%']=chart.plan_oil_tpd*.95
            chart['Допуск +5%']=chart.plan_oil_tpd*1.05
            melted=chart.melt(id_vars='timestamp',var_name='Показатель',value_name='Значение').dropna()
            limits=['Допуск −5%','Допуск +5%']
            st.altair_chart(alt.Chart(melted).mark_line(point=True).encode(
                x=alt.X('timestamp:T',title=None,axis=alt.Axis(format='%H:%M')),
                y=alt.Y('Значение:Q',title='Нефть, т/сут',scale=alt.Scale(zero=False)),
                color=alt.Color('Показатель:N'),
                strokeDash=alt.condition(alt.FieldOneOfPredicate(field='Показатель',oneOf=limits),alt.value([6,4]),alt.value([1,0])),
                tooltip=[alt.Tooltip('timestamp:T',format='%H:%M'),'Показатель:N',alt.Tooltip('Значение:Q',format='.2f')]
            ).properties(height=200),use_container_width=True)
        measurement_overview.render(root,separator,telemetry,hour)
        incidents=incident_view.opened_incidents(separator,hour)
        st.dataframe(incidents.rename(columns={'incident_id':'Инцидент','opened_hour':'Час обнаружения','signal':'Что обнаружено','observed_loss_tpd':'Недобор темпа, т/сут','status':'Статус'}),hide_index=True)
        if not incidents.empty:
            execution_states=autonomous_cycle.read_states(root,separator,telemetry,hour,incidents)
            names=incidents.incident_id.tolist()
            # Open the incident that still needs attention; closed ones stay one click away.
            waiting=[i for i,n in enumerate(names) if execution_states.get(n,{}).get('stage') not in ('approved_for_execution','closed_rejected')]
            selected=st.selectbox('Инцидент',names,index=waiting[0] if waiting else len(names)-1)
            execution_state=execution_states[selected]
            recommendation=execution_state.get('recommendation',{})
            plan=execution_state.get('plan',{})
            path=folder/'lifecycle.json'
            life=incident_lifecycle.ensure_incident(path,selected,'Причина определяется по измерениям')
            version=life['versions'][-1]
            row=incidents[incidents.incident_id==selected].iloc[0]
            incident_context={'incident_id':selected,'opened_hour':int(row.opened_hour),'observed_loss_tpd':float(row.observed_loss_tpd)}
            context,fingerprint=live_reasoning.snapshot(separator,telemetry,hour,incident_context,version.get('human_comment',''),version['version'],fingerprints(root))
            st.caption('Состояние агента: '+STAGE_LABELS.get(execution_state.get('stage'),str(execution_state.get('stage'))))
            recompute=execution_state.get('recompute')
            if recompute:
                label={'full':'полный (гипотезы, проверки, наборы, GAP)','network':'только сеть GAP по прежним наборам','none':'без расчётов: обновлены недобор и баланс'}[recompute['level']]
                st.caption(f"Пересчёт в этом часу: {label}. Последний полный расчёт — {recompute['basis_hour']:02d}:00. "+'; '.join(recompute['reasons']))
            if execution_state.get('stage')=='approved_for_execution':
                st.success('Решение утверждено. Эффекты выполняются по часам из локального реестра.')
            if execution_state.get('error') and execution_state.get('stage')!='waiting_license': st.error('Цикл остановлен: '+execution_state['error'])
            answer=execution_state.get('hypotheses')
            st.markdown('#### 3. Гипотезы: что могло случиться')
            if answer:
                st.write(russian_text(answer.get('assessment','')))
                readable_table([{'Гипотеза':item['title'],'Кандидаты':', '.join(item['candidate_wells']),
                                 'Обоснование':item['engineering_rationale'],'Как проверить':item['verification'],
                                 'Не хватает':'; '.join(item['missing_data'])} for item in answer['hypotheses']])
                st.caption('Гипотезы предлагает LLM по наблюдениям и доверию к скважинам. Это версии, а не установленные причины.')
            else:st.info('Гипотез для текущих данных ещё нет.')
            st.markdown('#### 4. Проверка гипотез расчётом')
            if execution_state.get('checks'):readable_table(check_table(execution_state['checks']))
            for fit in execution_state.get('adaptation',[]):
                with st.expander('PROSPER · варианты модели '+fit['well_id'],expanded=False):
                    if 'candidates' in fit:
                        st.dataframe(pd.DataFrame(fit['candidates']),hide_index=True)
                        st.caption(fit.get('interpretation',''))
                    else:st.write(fit.get('reason','Адаптация выполняется'))
            for assumption in execution_state.get('model_state',{}).get('assumptions',[]):st.caption('Состояние сети: '+assumption)
            st.caption('PROSPER проверяет, какая модель скважины согласуется с замером давления; физическую причину он не доказывает.')
            if plan:
                st.markdown('#### 5. Сколько нужно компенсировать')
                need=plan.get('need',{})
                if need.get('ready'):
                    st.write(f"К возможному началу эффекта в {need['effect_start_hour']:02d}:00 ожидается недобор {need['net_deficit_t']:.2f} т; на компенсацию остаётся {need['remaining_hours']} ч; требуется +{need['required_extra_oil_tpd']:.2f} т/сут.")
                    with st.expander('Как получена потребность'):
                        st.write(f"Накоплено до {hour:02d}:00: {need['completed_deficit_t']:.2f} т.")
                        st.write(f"За час реакции {hour:02d}:00–{need['effect_start_hour']:02d}:00: ещё {need['response_delay_deficit_t']:.2f} т.")
                        st.write(f"Текущая потеря темпа: {need['current_loss_tpd']:.2f} т/сут.")
                        st.write(f"Возврат накопленных {need['net_deficit_t']:.2f} т за {need['remaining_hours']} ч: +{need['recovery_component_tpd']:.2f} т/сут.")
                        st.code(f"{need['current_loss_tpd']:.2f} + {need['net_deficit_t']:.2f} × 24 / {need['remaining_hours']} = {need['required_extra_oil_tpd']:.2f} т/сут",language=None)
                    st.caption(need['assumption'])
                else: st.warning(need.get('reason','Недостаточно данных'))
                if 'proposal' in plan:
                    st.markdown('#### 6. Наборы мероприятий — сценарии для GAP')
                    names={'screen_single_wells':'скрининг одиночных скважин в GAP (матрица влияния)','calculate_sets':'полный расчёт наборов в GAP'}
                    for step in plan.get('tool_trace',[]):
                        text=f"Шаг {step['step']}: {names.get(step['tool'],step['tool'])}"
                        if step.get('reason'):text+=' — выбор агента: '+russian_text(step['reason'])
                        if step.get('result'):text+=' — итог: '+step['result']
                        st.caption(text)
                    for step in plan.get('tool_trace',[]):
                        if step.get('wells'):
                            with st.expander('Скрининг одиночных скважин: максимальный прирост каждой скважины в одиночку'):
                                st.dataframe(pd.DataFrame([{'Скважина':w['well_id'],'Прирост GAP, т/сут':w['gain_oil_tpd'],'Ограничения':'соблюдены' if w['constraints_met'] else 'нарушены','Закрывает потребность':'да' if w['covers_need'] else 'нет'} for w in step['wells']]),hide_index=True)
                    st.write(russian_text(plan['proposal']['assessment']))
                    readable_table([{'Набор':a['title'],'Почему выбран':a['rationale'],'Скважины':a['selected_wells'],
                                     'Что ещё проверить':a['unresolved_constraints'],
                                     'Сумма потенциалов реестра, т/сут':a.get('register_potential_sum_tpd')} for a in plan['proposal']['alternatives']])
                    for item in plan.get('mandatory_wells',[]):
                        st.info(item['well_id']+': '+item['reason']+' — скважина добавлена в каждый набор с регулированием в обе стороны.')
                    st.caption('Наборы выбирает LLM из реестра возможностей, в первую очередь скважины с высоким доверием. Потенциал реестра — не рассчитанный эффект.')
                if 'network' in plan or plan.get('network_error'):
                    st.markdown('#### 7. Расчёт GAP: точные режимы и ограничения')
                    if plan.get('network_error'):st.error('GAP: '+plan['network_error'])
                    if 'network' in plan:
                        readable_table([{'Набор':r['title'],'Прирост модели, т/сут':r.get('gain_oil_tpd'),'Условный баланс к 24:00, т':r.get('conditional_horizon_balance_t'),'Вода соблюдена':r.get('water_limit_met'),'Pзаб соблюдено':r.get('fbhp_limit_met'),'Мин. Pзаб, бар':r.get('minimum_fbhp_bar'),'Невязка нефти, т/сут':r.get('model_measurement_residual_tpd'),'Статус':r['interpretation']} for r in plan['network']['alternatives']])
                        for alternative in plan['network']['alternatives']:
                            with st.expander('Контроли GAP · '+alternative['title']):
                                st.dataframe(pd.DataFrame(alternative['configured_controls']),hide_index=True)
                    capacity=plan.get('capacity_check',{})
                    if capacity.get('network_error'):st.warning('Запасной расчёт всей регулирующей способности: '+capacity['network_error'])
                    for item in capacity.get('network',{}).get('alternatives',[]):
                        st.write(f"Запасной расчёт всей регулирующей способности: прирост {item.get('gain_oil_tpd',0):.2f} т/сут; ограничения соблюдены: {'да' if item.get('constraints_met') else 'нет'}.")
                    wash=plan.get('restoration_forecast')
                    if wash:
                        with st.expander('Сценарий промывки насоса по фазам',expanded=False):
                            if wash['ready']:
                                st.dataframe(pd.DataFrame(wash['timeline']),hide_index=True)
                                st.write('Ожидаемый баланс к концу суток, т:',wash['expected_horizon_balance_t'])
                                st.caption(wash['assumption'])
                            else:st.warning(wash['reason'])
                            for unresolved in wash.get('unresolved',[]):st.caption(unresolved)
            st.markdown('#### 8. Рекомендация')
            if recommendation.get('ready'):
                best=recommendation['selected']
                st.write('**'+best['title']+'**')
                st.write(f"Ожидаемый остаточный недобор к концу суток: {best['expected_deficit_t']:.2f} т. Если полностью закрыть недобор нельзя, показан лучший допустимый вариант.")
                st.dataframe(pd.DataFrame([{'Вариант':c['title'],'Остаточный недобор, т':c['expected_deficit_t'],'Баланс, т':c['expected_balance_t']} for c in recommendation['candidates']]),hide_index=True)
                st.caption(recommendation['basis'])
                for limitation in recommendation['limitations']+best['unresolved']:st.caption(limitation)
            elif life['stage']!='approved_for_execution':
                st.warning('Решение пока не готово: '+execution_state.get('reason',execution_state.get('error',plan.get('reason',recommendation.get('reason','Нет завершённого допустимого расчёта')))))
            st.markdown('#### 9. Решение инженера')
            covered=execution_state.get('field_plan',{}).get('incidents') or [selected]
            if len(covered)>1:
                st.info('План компенсации общий для инцидентов '+', '.join(covered)+': недобор сепаратора один на месторождение. Решение применяется ко всем этим инцидентам.')
            with st.form('live_decision'):
                decisions=['Утвердить','Вернуть на доработку','Отклонить'] if recommendation.get('ready') else ['Вернуть на доработку','Отклонить']
                decision=st.radio('Решение инженера',decisions)
                comment=st.text_input('Комментарий / новое ограничение')
                acknowledged=st.checkbox('Подтверждаю локальную имитацию и предварительный характер прогноза')
                submitted=st.form_submit_button('Зафиксировать',disabled=life['stage']=='approved_for_execution')
            if submitted:
                if decision=='Утвердить':
                    try:
                        if execution_state.get('fingerprint')!=fingerprint:raise ValueError('Данные изменились; требуется актуальное предложение')
                        live_execution.approve(root,covered,hour,fingerprint,recommendation,acknowledged)
                        for identity in covered:
                            incident_lifecycle.record_decision(path,identity,'Утверждено',comment,recommendation['selected']['title'],'Предварительный рассчитанный вариант; локальная имитация')
                        st.rerun()
                    except ValueError as error:st.error(str(error))
                elif decision=='Вернуть на доработку' and not comment.strip():
                    st.error('Укажите, что нужно изменить.')
                elif life['stage']=='awaiting_revision_calculation' and decision!='Отклонить':
                    st.error('Доработка уже запрошена; повторная версия пока не создаётся.')
                else:
                    status='На доработке' if decision=='Вернуть на доработку' else 'Отклонено'
                    for identity in covered:
                        incident_lifecycle.record_decision(path,identity,status,comment,None,'Нет проверенного предложения')
                    st.rerun()
            st.dataframe(pd.DataFrame(incident_lifecycle.version_rows(life)),hide_index=True)
    with st.expander('Журнал запусков агента'):
        runs=cycle_service.recent_runs(root)
        if runs:
            st.dataframe(pd.DataFrame([{'Запуск':r['run_id'],'Час':f"{r['hour']:02d}:00",'Итог':r['status'],'Длительность, с':r.get('duration_seconds'),
            'LLM':r.get('tools',{}).get('llm_calls'),'GAP':r.get('tools',{}).get('gap_runs'),'PROSPER':r.get('tools',{}).get('prosper_runs'),
            'Токены запроса (оценка)':r.get('tools',{}).get('llm_prompt_tokens_estimate'),
            'Стоимость LLM, $':r.get('tools',{}).get('llm_cost_usd'),
            'Инциденты':'; '.join(f"{k}: {v['stage']}"+(f" ({v['recompute']})" if v.get('recompute') else '') for k,v in r.get('incidents',{}).items()),
            'Ошибки':'; '.join(r.get('errors',[])+([r['tools']['limit_exceeded']] if r.get('tools',{}).get('limit_exceeded') else []))} for r in runs]),hide_index=True)
            st.caption('Лимиты такта — config/cycle_limits.json. Токены — оценка по длине запроса (символы / 4): Codex CLI не сообщает фактический расход.')
        else:st.caption('Запусков пока не было.')
    items=escalation.open_items(root,agent_hour=cycle_service.clock(root).get('hour'))
    with st.expander(f'Очередь эскалаций · открыто {len(items)}',expanded=bool(items)):
        if items:st.dataframe(pd.DataFrame([{'Что':i['subject'],'Причина':i['reason'],'Кому сейчас':i['current_role'],
            'Срок':i['deadline'].replace('T',' '),'Просрочено':'да' if i['overdue'] else 'нет','Час':f"{i['hour']:02d}:00",'Запуск':i['run_id']} for i in items]),hide_index=True)
        else:st.caption('Открытых эскалаций нет.')
        st.caption('Локальная очередь (data/live/escalations.json), уведомления не отправляются. Адресат и сроки — config/escalation.json.')
    with st.expander('Локальный реестр утверждений'):
        approvals=live_execution.approval_rows(root)
        if approvals:st.dataframe(pd.DataFrame(approvals),hide_index=True)
        else:st.caption('Утверждённых мероприятий пока нет.')
    with st.expander('Ограничения расчёта и доверие к скважинам'):
        limits=live_planning.constraints(root)
        controls=json.loads((root/'config'/'gap_optimization_case.json').read_text(encoding='utf-8'))['controls']
        st.write(f"Минимальное забойное давление: {limits['minimum_fbhp_bar']:g} бар (все работающие скважины сети).")
        st.write(f"Лимит воды: текущая вода сепаратора + {limits['water_margin_m3d']:g} м³/сут.")
        st.write(f"Частота ЭЦН: {controls['esp_absolute_min_hz']:g}–{controls['esp_absolute_max_hz']:g} Гц; скорость ШВН: {controls['pcp_absolute_min']:g}–{controls['pcp_absolute_max']:g}. Максимальное изменение по скважине — реестр возможностей.")
        st.caption('Настраивается в config/network_constraints.json и config/gap_optimization_case.json; действует со следующего такта агента.')
        if hour is not None:
            trust=well_trust.compute(root,telemetry,hour)
            if trust:
                st.dataframe(well_trust.table(trust),hide_index=True)
                st.caption('Доверие = KPI модели × KPI данных (config/well_trust.json). Низкое доверие — скважина не регулируется; в наборах в первую очередь выбираются скважины с высоким доверием.')
    with st.expander('Реестр возможностей'):
        st.dataframe(potential_register.table(root),hide_index=True)
        restoration=json.loads((root/'config'/'restoration_measures.json').read_text(encoding='utf-8'))
        st.markdown('Восстановительные мероприятия')
        for measure in restoration['measures']:
            st.write(measure['title'])
            st.dataframe(pd.DataFrame(measure['phases']),hide_index=True)
            st.caption(measure['assumption'])
