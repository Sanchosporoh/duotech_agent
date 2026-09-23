import tempfile
import unittest
from pathlib import Path
from src.calculation_result import completed, preserve_previous
from src.live_reasoning import save
from src import license_retry


class CalculationResultTests(unittest.TestCase):
    def test_only_finished_valid_output_is_reusable(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory)
            output=root/'result.json'; attempt=root/'attempt.json'
            save(output,{'alternatives':[]})
            self.assertFalse(completed(output,attempt))
            for stage in ['running','waiting_license','needs_attention','retry_requested']:
                save(attempt,{'stage':stage})
                self.assertFalse(completed(output,attempt))
            save(attempt,{'stage':'completed'})
            self.assertTrue(completed(output,attempt))
            output.write_text('{',encoding='utf-8')
            self.assertFalse(completed(output,attempt))
            self.assertEqual(license_retry.blocked(root,attempt)['stage'],'needs_attention')

    def test_retry_preserves_old_output_but_requires_new_file(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory); output=root/'result.json'
            save(output,{'old':True})
            preserve_previous(output)
            self.assertFalse(output.exists())
            saved=list(root.glob('result.json.previous-*'))
            self.assertEqual(len(saved),1)
            self.assertIn('old',saved[0].read_text(encoding='utf-8'))
            preserve_previous(output)
            self.assertEqual(len(list(root.iterdir())),1)

    def test_empty_lift_table_is_not_accepted(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory); output=root/'fitted.tpd'; attempt=root/'attempt.json'
            output.touch(); save(attempt,{'stage':'completed'})
            self.assertFalse(completed(output,attempt))
