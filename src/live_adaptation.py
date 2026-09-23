"""Dispatch configured physical fits using current observations only."""
import json
import hashlib
import pandas as pd
from src.live_reasoning import save
from src import license_retry, tool_gateway
from src.calculation_result import completed as result_completed, preserve_previous


def available_models(root):
    models=json.loads((root/'config/diagnostic_models.json').read_text(encoding='utf-8'))
    folder=root/'runtime/petex_case/IM_2022_06'
    if folder.exists():
        for path in folder.iterdir():
            if path.suffix.lower()=='.out':
                models.setdefault(path.stem+'_TLBB',{'working_model':str(path.relative_to(root))})
    return models


def run(root,context,key,answer):
    models=available_models(root)
    sensors=json.loads((root/'config'/'diagnostic_sensors.json').read_text(encoding='utf-8'))
    telemetry=pd.DataFrame(context['telemetry'])
    results=[]
    for well in sorted({w for h in answer['hypotheses'] for w in h['candidate_wells']}):
        if well not in models or 'working_model' not in models[well]:
            results.append({'well_id':well,'stage':'needs_data','reason':'Не подключена рабочая модель PROSPER'});continue
        history=telemetry[(telemetry.well_id==well)&(telemetry.hour<=context['hour'])].sort_values('hour') if 'well_id' in telemetry else pd.DataFrame()
        if history.empty:
            results.append({'well_id':well,'stage':'needs_data','reason':'Нет телеметрии указанной скважины'});continue
        current=history.iloc[-1]
        first=history.iloc[0]
        if current.hour!=context['hour']:
            results.append({'well_id':well,'stage':'needs_data','reason':'Нет свежей телеметрии. Текущее состояние скважины неизвестно.'});continue
        if current.get('frequency_hz')==0 and current.hour==context['hour']:
            results.append({'well_id':well,'stage':'screened','reason':'Свежий сигнал остановки: внести остановку в GAP; рабочий лифт не рассчитывается'});continue
        same_pressure=pd.notna(current.get('sensor_pressure_bar')) and pd.notna(first.get('sensor_pressure_bar')) and current.sensor_pressure_bar==first.sensor_pressure_bar
        same_control=(pd.isna(current.get('frequency_hz')) and pd.isna(first.get('frequency_hz'))) or (pd.notna(current.get('frequency_hz')) and pd.notna(first.get('frequency_hz')) and current.frequency_hz==first.frequency_hz)
        unchanged=same_pressure and same_control
        conditions_changed=any(pd.notna(current.get(f)) and pd.notna(first.get(f)) and current[f]!=first[f] for f in ['whp_bara','water_cut_pct','gor_m3m3'])
        if len(history)>1 and unchanged and not conditions_changed:
            results.append({'well_id':well,'stage':'screened','reason':'Давление не изменилось; '+('текущий контроль отсутствует — используем модельный как допущение' if pd.isna(current.get('frequency_hz')) else 'доступная частота не изменилась')+'. Исходное состояние модели — допущение, скважина не исключена из гипотез'});continue
        if well not in sensors:
            results.append({'well_id':well,'stage':'needs_data','reason':'Файл модели найден, но положение датчика и допуск давления не подтверждены'});continue
        fields=['frequency_hz','sensor_pressure_bar','whp_bara','water_cut_pct','gor_m3m3']
        if current.hour!=context['hour'] or any(pd.isna(current.get(f)) for f in fields) or current.frequency_hz<=0:
            results.append({'well_id':well,'stage':'needs_data','reason':'Нет полного текущего набора условий работающего насоса'});continue
        folder=root/'data'/'live'/'adaptation'/('dispatch_v2_'+key)/well
        output=folder/'result.json';attempt=folder/'attempt.json'
        if result_completed(output,attempt):results.append(json.loads(output.read_text(encoding='utf-8')));continue
        waiting=license_retry.blocked(root,attempt)
        if waiting:results.append(dict(waiting,well_id=well));continue
        request={f:float(current[f]) for f in fields}
        request.update(well_id=well,working_model=models[well]['working_model'],tolerance_bar=sensors[well]['pressure_residual_tolerance_bar'])
        preserve_previous(output)
        save(folder/'request.json',request);save(attempt,{'well_id':well,'stage':'running'})
        completed=tool_gateway.run_worker(root,'fit_live_prosper',folder/'request.json',output)
        if completed.returncode or not output.exists():
            error=dict(license_retry.failure(root,(completed.stderr or completed.stdout)[-2000:]),well_id=well)
            save(attempt,error);results.append(error)
        else:
            license_retry.success(root)
            results.append(json.loads(output.read_text(encoding='utf-8')))
            save(attempt,{'stage':'completed','well_id':well})
    return results


def prepare_lifts(root,context,adaptation):
    """Prepare provisional lift tables; do not resolve ambiguous diagnoses by fiat."""
    models=available_models(root)
    telemetry=pd.DataFrame(context['telemetry'])
    tables=[]
    assumptions=[]
    for fit in adaptation:
        if fit.get('stage')=='screened':
            assumptions.append(fit['well_id']+': '+fit['reason'])
            continue
        compatible=[c for c in fit.get('candidates',[]) if c.get('pressure_compatible')]
        if not compatible:
            return {'ready':False,'stage':fit.get('stage','needs_data'),'reason':fit['well_id']+': '+fit.get('reason','Нет согласованного с давлением варианта модели'),'well_id':fit['well_id']}
        if len(compatible)!=1:
            return {'ready':False,'reason':'Несколько вариантов согласованы с давлением; единственная характеристика сети не определена','well_id':fit['well_id']}
        candidate=compatible[0]
        if candidate['kind'] not in ['pump','unchanged']:
            return {'ready':False,'reason':'Для изменения притока требуется передача IPR, а не только VLP','well_id':fit['well_id']}
        well=fit['well_id']
        signal=telemetry[telemetry.well_id==well].sort_values('hour').iloc[-1]
        request={f:float(signal[f]) for f in ['frequency_hz','sensor_pressure_bar','whp_bara','water_cut_pct','gor_m3m3']}
        request.update(working_model=models[well]['working_model'],candidate=candidate,**tool_gateway.cache_marker())
        digest=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()
        folder=root/'data'/'live'/'lift_tables'/digest
        output=folder/'fitted.tpd';attempt=folder/'attempt.json'
        if not result_completed(output,attempt):
            waiting=license_retry.blocked(root,attempt)
            if waiting:return dict(waiting,ready=False)
            preserve_previous(output)
            save(folder/'request.json',request);save(attempt,{'stage':'running'})
            completed=tool_gateway.run_worker(root,'export_live_vlp',folder/'request.json',output)
            if completed.returncode or not output.exists():
                reason=(completed.stderr or completed.stdout)[-2000:]
                error=license_retry.failure(root,reason)
                save(attempt,error)
                return dict(error,ready=False)
            license_retry.success(root)
            save(attempt,{'stage':'completed'})
        tables.append({'well_id':well,'path':str(output.resolve()),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'candidate':candidate})
    return {'ready':bool(tables) or bool(assumptions),'lift_tables':tables,'assumptions':assumptions,'reason':'Предварительное состояние сети; допущения по непроверенным объектам перечислены отдельно'}
