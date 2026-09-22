import unittest
from pathlib import Path
from src.live_checks import execute

ROOT=Path(__file__).resolve().parents[1]


class LiveChecksTests(unittest.TestCase):
    def test_changed_water_cut_blocks_old_curve(self):
        context={'hour':6,'telemetry':[{'hour':0,'well_id':'W_BEL_27_TLBB','frequency_hz':60},{'hour':6,'well_id':'W_BEL_27_TLBB','frequency_hz':60,'sensor_pressure_bar':104,'water_cut_pct':50}]}
        rows=execute(ROOT,context,self.answer('W_BEL_27_TLBB'))
        self.assertTrue(any('Изменились' in r['Результат / что требуется'] for r in rows))
        self.assertFalse(any(r['Инструмент']=='Прежний лифт' for r in rows))
    def answer(self,well):
        return {'hypotheses':[{'title':'Произвольная гипотеза','candidate_wells':[well],'verification':'Проверить'}]}

    def test_unconnected_well_does_not_get_w27_result(self):
        context={'hour':3,'telemetry':[{'hour':0,'well_id':'arbitrary','frequency_hz':60},{'hour':3,'well_id':'arbitrary','frequency_hz':60,'sensor_pressure_bar':105}]}
        rows=execute(ROOT,context,self.answer('arbitrary'))
        self.assertTrue(any('не подключены' in r['Результат / что требуется'] for r in rows))
        self.assertFalse(any(r['Статус']=='Условная оценка' for r in rows))

    def test_stale_signal_blocks_model_check(self):
        context={'hour':4,'telemetry':[{'hour':3,'well_id':'W_BEL_27_TLBB','frequency_hz':60,'sensor_pressure_bar':105}]}
        rows=execute(ROOT,context,self.answer('W_BEL_27_TLBB'))
        self.assertEqual(rows[0]['Инструмент'],'Свежесть')

    def test_current_pressure_is_used_for_registered_model(self):
        context={'hour':6,'telemetry':[{'hour':0,'well_id':'W_BEL_27_TLBB','frequency_hz':60,'sensor_pressure_bar':100},{'hour':6,'well_id':'W_BEL_27_TLBB','frequency_hz':60,'sensor_pressure_bar':104.14}]}
        rows=execute(ROOT,context,self.answer('W_BEL_27_TLBB'))
        self.assertEqual(sum(r['Статус']=='Условная оценка' for r in rows),2)
