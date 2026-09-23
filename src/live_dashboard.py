"""Editable measurement-driven dashboard; prepared cases are only input fixtures."""
from datetime import datetime
import json
import pandas as pd
import streamlit as st
import altair as alt
from src import incident_view, incident_lifecycle, live_monitor, potential_register, live_reasoning, live_checks
from src import autonomous_cycle, cycle_service, live_execution, license_retry, tool_gateway
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


@st.fragment(run_every='10s')
def agent_watch(root,seen):
    # The agent runs in its own process; refresh the page when it has processed a new hour.
    if cycle_service.clock(root).get('updated_at')!=seen:st.rerun()


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
    agent_watch(root,agent.get('updated_at'))
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
            selected=st.selectbox('Инцидент',incidents.incident_id.tolist())
            execution_state=execution_states[selected]
            recommendation=execution_state.get('recommendation',{})
            for assumption in execution_state.get('model_state',{}).get('assumptions',[]):st.caption(assumption)
            if recommendation.get('ready'):
                st.markdown('#### Рекомендация')
                best=recommendation['selected']
                st.write(best['title'])
                st.write(f"Ожидаемый остаточный недобор: {best['expected_deficit_t']:.2f} т. Полное закрытие недобора не является условием выдачи предложения.")
                st.caption(recommendation['basis'])
                st.dataframe(pd.DataFrame([{'Вариант':c['title'],'Остаточный недобор, т':c['expected_deficit_t'],'Баланс, т':c['expected_balance_t']} for c in recommendation['candidates']]),hide_index=True)
                for limitation in recommendation['limitations']+best['unresolved']:st.caption(limitation)
            if execution_state.get('stage')=='approved_for_execution':
                st.success('Решение утверждено. Эффекты выполняются по часам из локального реестра.')
            if execution_state.get('error') and execution_state.get('stage')!='waiting_license': st.error('Цикл остановлен: '+execution_state['error'])
            st.caption('Состояние агента: '+{'pending':'Агент ещё не обработал текущие данные','needs_data':'Недостаточно данных для расчёта','waiting_license':'Ожидание лицензии OpenServer','running':'Расчёт выполняется','needs_attention':'Работа остановлена — причина указана ниже','awaiting_human_decision':'Предложение готово, требуется утверждение','awaiting_model_state':'Недостаточно данных для расчёта сети','conditional_network_calculated':'Сеть рассчитана, результаты предварительные','approved_for_execution':'Решение утверждено'}.get(execution_state.get('stage'),str(execution_state.get('stage'))))
            if not recommendation.get('ready'):
                st.warning('Решение пока не готово: '+execution_state.get('reason',execution_state.get('error',execution_state.get('plan',{}).get('reason',recommendation.get('reason','Нет завершённого допустимого расчёта')))))
            st.markdown('#### Рассмотренные скважины — признаки и доступность данных')
            st.caption('Потеря на сепараторе не определяет скважину. Ни одна скважина не исключается только из-за отсутствия изменений телеметрии.')
            readable_table(live_monitor.screen_wells(telemetry,hour))
            for fit in execution_state.get('adaptation',[]):
                with st.expander('Варианты адаптации · '+fit['well_id'],expanded=True):
                    if 'candidates' in fit:
                        st.dataframe(pd.DataFrame(fit['candidates']),hide_index=True)
                        st.caption(fit['interpretation'])
                    else:st.warning(fit.get('reason','Адаптация выполняется'))
            plan=execution_state.get('plan',{})
            if plan:
                st.markdown('#### Предварительная потребность и наборы для расчёта ИМА')
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
                    st.write(russian_text(plan['proposal']['assessment']))
                    proposal_rows=[{'Набор':a['title'],'Почему выбран':a['rationale'],'Скважины':a['selected_wells'],
                                    'Что ещё проверить':a['unresolved_constraints'],
                                    'Сумма потенциалов реестра, т/сут':a.get('register_potential_sum_tpd')} for a in plan['proposal']['alternatives']]
                    readable_table(proposal_rows)
                    st.caption('Суммы потенциала и стоимости взяты из реестра. Это не рассчитанный эффект, не точные режимы и не разрешение на исполнение.')
                st.info(plan.get('reason','Необходимо уточнить данные'))
                if plan.get('network_error'):st.error('GAP: '+plan['network_error'])
                wash=plan.get('restoration_forecast')
                if wash:
                    with st.expander('Прогноз промывки насоса',expanded=True):
                        if wash['ready']:
                            st.dataframe(pd.DataFrame(wash['timeline']),hide_index=True)
                            st.write('Ожидаемый баланс к концу суток, т:',wash['expected_horizon_balance_t'])
                            st.caption(wash['assumption'])
                        else:st.warning(wash['reason'])
                        for unresolved in wash.get('unresolved',[]):st.caption(unresolved)
                capacity=plan.get('capacity_check',{})
                if capacity.get('network_error'):st.warning('Проверка всех возможностей: '+capacity['network_error'])
                for item in capacity.get('network',{}).get('alternatives',[]):
                    st.write('Проверка всех доступных регулирований: прирост',item.get('gain_oil_tpd'),'т/сут; ограничения соблюдены:',item.get('constraints_met'),'условная цель достигнута:',item.get('conditional_target_met'))
                if 'network' in plan:
                    readable_table([{'Набор':r['title'],'Прирост модели, т/сут':r.get('gain_oil_tpd'),'Невязка нефти, т/сут':r.get('model_measurement_residual_tpd'),'Невязка воды, м³/сут':r.get('model_measurement_water_residual_m3d'),'Условный баланс к 24:00, т':r.get('conditional_horizon_balance_t'),'Вода соблюдена':r.get('water_limit_met'),'Pзаб соблюдено':r.get('fbhp_limit_met'),'Статус':r['interpretation']} for r in plan['network']['alternatives']])
                    for alternative in plan['network']['alternatives']:
                        with st.expander('Контроли GAP · '+alternative['title']):
                            st.dataframe(pd.DataFrame(alternative['configured_controls']),hide_index=True)
            st.markdown('#### Версии по явным изменениям телеметрии — не подтверждённые причины')
            checks=live_monitor.hypotheses(telemetry,hour)
            with st.expander('Подробные признаки телеметрии'):
                readable_table(checks.rename(columns={'well_id':'Скважина','hypothesis':'Версия','pressure_delta_bar':'Изменение давления, бар','frequency_hz':'Частота, Гц','measurement_hour':'Час замера','status':'Вывод'}))
            basic_answer={'hypotheses':[{'title':r.hypothesis,'candidate_wells':[] if r.well_id=='—' else [r.well_id],
                                       'verification':'Собрать независимые измерения'} for _,r in checks.iterrows()]}
            basic_context={'hour':hour,'telemetry':json.loads(telemetry[telemetry.hour<=hour].to_json(orient='records',date_format='iso'))}
            with st.expander('Подробные базовые проверки сигналов и исходных характеристик',expanded=False):
                readable_table(check_table(live_checks.execute(root,basic_context,basic_answer)))
            st.caption('Номер инцидента не выбирает скважину, причину или готовый расчёт. Здесь показаны признаки текущего часа, не подтверждённые гипотезы.')
            path=folder/'lifecycle.json'
            life=incident_lifecycle.ensure_incident(path,selected,'Причина определяется по измерениям')
            version=life['versions'][-1]
            row=incidents[incidents.incident_id==selected].iloc[0]
            incident_context={'incident_id':selected,'opened_hour':int(row.opened_hour),'observed_loss_tpd':float(row.observed_loss_tpd)}
            context,fingerprint=live_reasoning.snapshot(separator,telemetry,hour,incident_context,version.get('human_comment',''),version['version'],fingerprints(root))
            response_path=folder/'reasoning'/f'{fingerprint}.json'
            if response_path.exists():
                result=json.loads(response_path.read_text(encoding='utf-8'))
                st.write(result['answer']['assessment'])
                hypothesis_rows=[{'Гипотеза':item['title'],'Кандидаты':', '.join(item['candidate_wells']),
                                  'Обоснование':item['engineering_rationale'],'Проверка':item['verification'],
                                  'Не хватает':'; '.join(item['missing_data'])} for item in result['answer']['hypotheses']]
                readable_table(hypothesis_rows)
                st.caption('Ответ относится только к текущим данным, часу и версии комментария. При их изменении требуется новый анализ.')
                st.markdown('#### Проверки гипотез — что сделали и что установили')
                checks_result=live_checks.execute(root,context,result['answer'])
                readable_table(check_table(checks_result))
                st.caption('Это ограниченный набор проверок, а не исполнение любого текста Codex. Прежние кривые используются только для подключённых объектов и совместимых контролей. Условная оценка не подтверждает причину.')
            else:
                st.warning('Для текущего снимка данных актуального ответа Codex нет.')
            if not recommendation.get('ready') and life['stage']!='approved_for_execution':
                st.info('Утверждение недоступно: нет актуального допустимого предложения.')
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
                        live_execution.approve(root,selected,hour,fingerprint,recommendation,acknowledged)
                        incident_lifecycle.record_decision(path,selected,'Утверждено',comment,recommendation['selected']['title'],'Предварительный рассчитанный вариант; локальная имитация')
                        st.rerun()
                    except ValueError as error:st.error(str(error))
                elif decision=='Вернуть на доработку' and not comment.strip():
                    st.error('Укажите, что нужно изменить.')
                elif life['stage']=='awaiting_revision_calculation' and decision!='Отклонить':
                    st.error('Доработка уже запрошена; повторная версия пока не создаётся.')
                else:
                    status='На доработке' if decision=='Вернуть на доработку' else 'Отклонено'
                    incident_lifecycle.record_decision(path,selected,status,comment,None,'Нет проверенного предложения')
                    st.rerun()
            st.dataframe(pd.DataFrame(incident_lifecycle.version_rows(life)),hide_index=True)
    with st.expander('Журнал запусков агента'):
        runs=cycle_service.recent_runs(root)
        if runs:st.dataframe(pd.DataFrame([{'Запуск':r['run_id'],'Час':f"{r['hour']:02d}:00",'Итог':r['status'],'Длительность, с':r.get('duration_seconds'),
            'Инциденты':'; '.join(f"{k}: {v['stage']}" for k,v in r.get('incidents',{}).items()),'Ошибки':'; '.join(r.get('errors',[]))} for r in runs]),hide_index=True)
        else:st.caption('Запусков пока не было.')
    with st.expander('Локальный реестр утверждений'):
        approvals=live_execution.approval_rows(root)
        if approvals:st.dataframe(pd.DataFrame(approvals),hide_index=True)
        else:st.caption('Утверждённых мероприятий пока нет.')
    with st.expander('Реестр возможностей'):
        st.dataframe(potential_register.table(root),hide_index=True)
        restoration=json.loads((root/'config'/'restoration_measures.json').read_text(encoding='utf-8'))
        st.markdown('Восстановительные мероприятия')
        for measure in restoration['measures']:
            st.write(measure['title'])
            st.dataframe(pd.DataFrame(measure['phases']),hide_index=True)
            st.caption(measure['assumption'])
