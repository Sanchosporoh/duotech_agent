import unittest
from pathlib import Path
import pandas as pd
from streamlit.testing.v1 import AppTest
from src.measurement_overview import well_statuses,baseline_allocation,balance_history

ROOT=Path(__file__).resolve().parents[1]


class OverviewTests(unittest.TestCase):
    def test_initial_match_does_not_hide_later_loss(self):
        allocation=pd.DataFrame({'Скважина':['A','B'],'Исходная оценка нефти, т/сут':[60,40]})
        separator=pd.DataFrame({'hour':[0,1,2],'separator_oil_tpd':[110,100,80]})
        parts,history,factor=balance_history(allocation,separator,1)
        self.assertAlmostEqual(parts['Оценочный вклад, т/сут'].sum(),110)
        self.assertAlmostEqual(factor,1.1)
        self.assertEqual(history['Расхождение, т/сут'].tolist(),[0,-10])

    def test_future_is_not_visible_and_stale_is_unknown(self):
        frame=pd.DataFrame([
            dict(hour=0,well_id='A',sensor_pressure_bar=100,frequency_hz=50),
            dict(hour=6,well_id='A',sensor_pressure_bar=105,frequency_hz=50)])
        self.assertIn('Нет явной',well_statuses(frame,0).iloc[0]['Состояние'])
        self.assertIn('Недостаточно',well_statuses(frame,5).iloc[0]['Состояние'])
        self.assertIn('Изменение',well_statuses(frame,6).iloc[0]['Состояние'])

    def test_density_conversion(self):
        allocation=baseline_allocation(ROOT)
        self.assertAlmostEqual(allocation.iloc[0]['Исходная оценка нефти, т/сут'],33.772876406*.908)

    def test_overview_renders_and_selects_well(self):
        app=AppTest.from_string(f"from pathlib import Path\nimport pandas as pd\nfrom src.measurement_overview import render\nr=Path({str(ROOT)!r})\ns=pd.read_csv(r/'data/live/separator.csv',parse_dates=['timestamp'])\nt=pd.read_csv(r/'data/live/telemetry.csv',parse_dates=['timestamp'])\nrender(r,s,t,6)")
        app.run(timeout=20)
        self.assertFalse(app.exception)
        self.assertGreater(len(app.selectbox[0].options),1)
        app.selectbox[0].select(app.selectbox[0].options[1]).run(timeout=20)
        self.assertFalse(app.exception)
