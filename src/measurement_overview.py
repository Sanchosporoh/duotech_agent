"""Read-only engineering overview; never infer allocation from a separator total."""
import pandas as pd
import streamlit as st
import altair as alt
import math
from src import live_monitor


def well_statuses(telemetry, hour):
    frame=live_monitor.screen_wells(telemetry,hour)
    if frame.empty:return frame
    def status(row):
        reason=row['Почему рассматриваем / чего не знаем']
        if 'сигнал остановки' in reason:return '🔴 Сигнал остановки'
        if 'Давление изменилось' in reason or 'Частота:' in reason:return '🟠 Изменение сигналов'
        if 'назад' in reason or 'Нет давления' in reason:return '⚪ Недостаточно данных'
        return '🟢 Нет явной аномалии'
    frame.insert(1,'Состояние',frame.apply(status,axis=1))
    priority={'🔴 Сигнал остановки':0,'🟠 Изменение сигналов':1,'⚪ Недостаточно данных':2,'🟢 Нет явной аномалии':3}
    return frame.assign(_priority=frame['Состояние'].map(priority)).sort_values(['_priority','Скважина']).drop(columns='_priority').reset_index(drop=True)


def allocation_tiles(allocation, measured):
    """Areas encode magnitudes; the signed residual is not assigned to any well."""
    entries=[{'name':str(r['Скважина']),'value':float(r['Оценочный вклад, т/сут']),'gap':False} for _,r in allocation.iterrows()
             if pd.notna(r['Оценочный вклад, т/сут']) and float(r['Оценочный вклад, т/сут'])>0]
    total=sum(e['value'] for e in entries)
    if measured is not None and math.isfinite(float(measured)):
        residual=float(measured)-total
        if abs(residual)>1e-6:
            entries.append({'name':'Избыток' if residual>0 else 'Недостаток','value':abs(residual),'signed':residual,'gap':True})
    entries.sort(key=lambda e:(-e['value'],e['name']))
    rows=[]
    def place(items,x,y,w,h):
        if not items:return
        if len(items)==1:
            e=items[0];name=e['name'];short=name.removeprefix('W_BEL_').removesuffix('_TLBB')
            rows.append({'Объект':name,'Нефть, т/сут':e.get('signed',e['value']),'gap':e['gap'],
                         'x':x,'x2':x+w,'y':y,'y2':y+h,
                         'label':(name if e['gap'] else 'Скв. '+short) if w>65 and h>30 else '',
                         'amount':f"{e.get('signed',e['value']):+.2f}" if e['gap'] else f"{e['value']:.2f}"})
            return
        total=sum(i['value'] for i in items);running=0;cuts=[]
        for k,item in enumerate(items[:-1],1):
            running+=item['value'];cuts.append((abs(running-total/2),k,running))
        _,k,part=min(cuts);ratio=part/total
        if w>=h:
            place(items[:k],x,y,w*ratio,h);place(items[k:],x+w*ratio,y,w*(1-ratio),h)
        else:
            place(items[:k],x,y,w,h*ratio);place(items[k:],x,y+h*ratio,w,h*(1-ratio))
    place(entries,0,0,1000,320)
    return pd.DataFrame(rows)


def baseline_allocation(root):
    path=root/'data/petex_baseline.csv'
    if not path.exists():return pd.DataFrame()
    source=pd.read_csv(path)
    valid=source[(source.oil_rate_unit=='Sm3/day') & (source.sog_unit=='Kg/m3')].copy()
    valid['Исходная оценка нефти, т/сут']=valid.oil_rate*valid.sog/1000
    return valid[['well_id','Исходная оценка нефти, т/сут']].rename(columns={'well_id':'Скважина'})


def balance_history(allocation, separator, hour):
    visible=separator[separator.hour<=hour].sort_values('hour').copy()
    measured=visible.dropna(subset=['separator_oil_tpd'])
    total=allocation['Исходная оценка нефти, т/сут'].sum()
    if measured.empty or total<=0:return pd.DataFrame(),pd.DataFrame(),None
    anchor=float(measured.iloc[0].separator_oil_tpd)
    factor=anchor/total
    parts=allocation.copy()
    parts['Оценочный вклад, т/сут']=parts['Исходная оценка нефти, т/сут']*factor
    visible['Сумма исходных вкладов']=anchor
    visible['Расхождение, т/сут']=visible.separator_oil_tpd-anchor
    return parts,visible,factor


def render(root, separator, telemetry, hour):
    st.markdown('#### 1. Что изменилось в телеметрии')
    statuses=well_statuses(telemetry,hour)
    if statuses.empty:
        st.info('Доступной телеметрии пока нет.')
        return
    left,right=st.columns([1,1.3])
    with left:
        st.dataframe(statuses[['Скважина','Состояние','Последний замер']],hide_index=True,height=220)
        selected=st.selectbox('Посмотреть скважину',statuses['Скважина'].tolist(),key='overview_well')
        row=statuses[statuses['Скважина']==selected].iloc[0]
        st.write(row['Почему рассматриваем / чего не знаем'])
    with right:
        history=telemetry[(telemetry.hour<=hour)&(telemetry.well_id==selected)].sort_values('hour')
        labels={'sensor_pressure_bar':'Давление датчика, бар','frequency_hz':'Частота ЭЦН, Гц','esp_current_a':'Ток, А','vibration_mm_s':'Вибрация, мм/с'}
        available=[key for key in labels if key in history and history[key].notna().any()]
        if available:
            parameter=st.selectbox('Показатель',available,format_func=lambda key:labels[key],key='overview_parameter')
            chart=alt.Chart(history.dropna(subset=[parameter])).mark_line(point=True).encode(
                x=alt.X('timestamp:T',title=None,axis=alt.Axis(format='%H:%M')),
                y=alt.Y(f'{parameter}:Q',title=labels[parameter],scale=alt.Scale(zero=False)),
                tooltip=[alt.Tooltip('timestamp:T',format='%H:%M'),alt.Tooltip(f'{parameter}:Q',format='.2f')]).properties(height=180)
            st.altair_chart(chart,use_container_width=True)
        else:st.info('Нет значений для графика.')
        st.caption('Изменение сигнала — повод для проверки, а не установленная причина. Отсутствие аномалии не исключает снижение дебита.')
    with st.expander('2. Из чего складывается добыча сепаратора',expanded=True):
        allocation=baseline_allocation(root)
        if allocation.empty:
            st.info('Нет исходных оценок дебитов скважин. Распределение не построено.')
            return
        allocation,visible,factor=balance_history(allocation,separator,hour)
        if visible.empty:
            st.info('Нет доступного замера сепаратора для сравнения.')
            return
        latest=visible.iloc[-1]
        measured=latest.separator_oil_tpd if int(latest.hour)==hour and pd.notna(latest.separator_oil_tpd) else None
        tiles=allocation_tiles(allocation,measured)
        if not tiles.empty:
            names=sorted(allocation['Скважина'].tolist())
            palette=['#2563eb','#0d9488','#7c3aed','#d97706','#db2777','#0891b2','#4f46e5','#65a30d','#9333ea','#ea580c','#0284c7','#059669','#c026d3','#ca8a04','#6366f1','#16a34a','#be185d']
            base=alt.Chart(tiles).encode(
                x=alt.X('x:Q',axis=None,scale=alt.Scale(domain=[0,1000])),
                x2='x2:Q',y=alt.Y('y:Q',axis=None,scale=alt.Scale(domain=[320,0])),y2='y2:Q')
            rectangles=base.mark_rect(stroke='white',strokeWidth=2).encode(
                color=alt.condition(alt.datum.gap,alt.value('#000000'),alt.Color('Объект:N',legend=None,scale=alt.Scale(domain=names,range=[palette[i%len(palette)] for i in range(len(names))]))),
                tooltip=['Объект:N',alt.Tooltip('Нефть, т/сут:Q',format='+.2f')])
            text=alt.Chart(tiles[tiles.label!='']).transform_calculate(cx='(datum.x+datum.x2)/2',cy='(datum.y+datum.y2)/2').encode(
                x=alt.X('cx:Q',axis=None,scale=alt.Scale(domain=[0,1000])),
                y=alt.Y('cy:Q',axis=None,scale=alt.Scale(domain=[320,0])))
            tile_labels=text.mark_text(color='white',fontSize=13,fontWeight='bold',dy=-8).encode(text='label:N')
            amounts=text.mark_text(color='white',fontSize=12,dy=10).encode(text='amount:N')
            st.altair_chart((rectangles+tile_labels+amounts).properties(height=320).configure_view(stroke=None),use_container_width=True)
        total=allocation['Оценочный вклад, т/сут'].sum()
        a,b,c=st.columns(3)
        a.metric('Сумма оценок скважин, т/сут',f'{total:.2f}')
        b.metric(f'Сепаратор · {hour:02d}:00, т/сут','Нет замера' if measured is None else f'{measured:.2f}')
        c.metric('Невязка, т/сут','Не определена' if measured is None else f'{measured-total:+.2f}')
        st.caption('Площадь цветной плитки пропорциональна исходной оценке скважины. Чёрная плитка — модуль разницы «сепаратор − сумма оценок» со знаком в подписи, а не дополнительная скважина. Потеря не приписывается конкретному объекту без диагностики.')
        if measured is None:st.warning('Нет текущего замера сепаратора: чёрная плитка не строится.')
        elif abs(measured-total)<1e-6:st.caption('Баланс совпадает: чёрной плитки нет.')
        st.caption(f'Исходные вклады согласованы с первым доступным замером, коэффициент {factor:.4f}. Это опорные оценки, не текущие индивидуальные замеры.')
        with st.expander('История баланса и подробные значения',expanded=False):
            comparison=visible[['timestamp','separator_oil_tpd','Сумма исходных вкладов']].rename(columns={'separator_oil_tpd':'Измерение сепаратора'}).melt(id_vars='timestamp',var_name='Показатель',value_name='Нефть, т/сут').dropna()
            st.altair_chart(alt.Chart(comparison).mark_line(point=True).encode(
                x=alt.X('timestamp:T',axis=alt.Axis(format='%H:%M'),title=None),
                y=alt.Y('Нефть, т/сут:Q',scale=alt.Scale(zero=False)),
                color='Показатель:N',
                tooltip=[alt.Tooltip('timestamp:T',format='%H:%M'),'Показатель:N',alt.Tooltip('Нефть, т/сут:Q',format='.2f')]).properties(height=200),use_container_width=True)
            st.dataframe(allocation[['Скважина','Оценочный вклад, т/сут']],hide_index=True)
