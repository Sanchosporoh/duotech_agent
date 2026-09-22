import tempfile
import unittest
from pathlib import Path
import json
from src import license_retry


class LicenseRetryTests(unittest.TestCase):
    def test_interrupted_worker_retries_only_after_process_lock_is_free(self):
        from src.cycle_lock import acquire
        from src.live_reasoning import save
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); attempt=root/'attempt.json'
            save(attempt,{'stage':'running'})
            with acquire(root,'petex.lock') as locked:
                self.assertTrue(locked)
                self.assertEqual(license_retry.blocked(root,attempt)['stage'],'running')
            self.assertIsNone(license_retry.blocked(root,attempt))

    def test_delay_backoff_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'config').mkdir()
            (root/'config/license_retry.json').write_text(json.dumps({'initial_delay_seconds':60,'maximum_delay_seconds':900}),encoding='utf-8')
            error=license_retry.failure(root,'No OpenServer license available',now=100)
            self.assertEqual(error['retry_at_epoch'],160)
            self.assertIsNotNone(license_retry.blocked(root,now=159))
            self.assertIsNone(license_retry.blocked(root,now=160))
            error=license_retry.failure(root,'No OpenServer license available',now=160)
            self.assertEqual(error['delay_seconds'],120)
            license_retry.success(root)
            self.assertIsNone(license_retry.blocked(root,now=161))

    def test_missing_model_does_not_trigger_license_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            result=license_retry.failure(root,'Не подключена рабочая модель PROSPER')
            self.assertEqual(result['stage'],'needs_attention')
            self.assertEqual(license_retry.state(root),{})
