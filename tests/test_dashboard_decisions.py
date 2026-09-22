"""Exercise HITL form without modifying project decision history."""
import json
from pathlib import Path
import tempfile
import unittest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


class DashboardDecisionTests(unittest.TestCase):
    def make_app(self, folder):
        source = (ROOT / 'dashboard.py').read_text(encoding='utf-8')
        # Regression coverage for the old form retained below the live entry point.
        start = source.index("for module_name in ('live_monitor'")
        end = source.index('st.stop()\n', start) + len('st.stop()\n')
        source = source[:start] + source[end:]
        source = source.replace('ROOT = Path(__file__).resolve().parent', f'ROOT = Path({str(ROOT)!r})')
        source = source.replace('lifecycle_path=ROOT/"data"/"incident_lifecycle.json"',
                                f'lifecycle_path=Path({str(Path(folder)/"lifecycle.json")!r})')
        source = source.replace('log=ROOT/"data"/"approval_log.csv"',
                                f'log=Path({str(Path(folder)/"approval_log.csv")!r})')
        app = AppTest.from_string(source)
        app.session_state['simulation_hour'] = 6
        app.run(timeout=30)
        self.assertFalse(app.exception)
        return app

    def submit(self, app, decision, comment=''):
        next(r for r in app.radio if r.label == 'Решение инженера').set_value(decision)
        next(t for t in app.text_input if t.label == 'Комментарий / новое ограничение').set_value(comment)
        button = next(b for b in app.button if b.label == 'Зафиксировать')
        self.assertFalse(button.disabled)
        button.click().run(timeout=30)
        self.assertFalse(app.exception)

    def test_return_with_comment_is_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            app = self.make_app(folder)
            self.submit(app, 'Вернуть на доработку', 'Пересмотреть набор скважин')
            incident = json.loads((Path(folder)/'lifecycle.json').read_text(encoding='utf-8'))['incidents']['INC-001']
            self.assertEqual(incident['stage'], 'awaiting_revision_calculation')
            self.assertEqual(incident['versions'][-1]['human_comment'], 'Пересмотреть набор скважин')

    def test_empty_comment_is_not_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            app = self.make_app(folder)
            self.submit(app, 'Вернуть на доработку')
            self.assertTrue(app.error)
            self.assertFalse((Path(folder)/'approval_log.csv').exists())

    def test_reject_is_saved_even_when_approval_is_not_allowed(self):
        with tempfile.TemporaryDirectory() as folder:
            app = self.make_app(folder)
            self.submit(app, 'Отклонить', 'Не подходит')
            incident = json.loads((Path(folder)/'lifecycle.json').read_text(encoding='utf-8'))['incidents']['INC-001']
            self.assertEqual(incident['stage'], 'closed_rejected')


if __name__ == '__main__':
    unittest.main()
