import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from src.cycle_lock import acquire


class CycleLockTests(unittest.TestCase):
    def test_second_opener_of_a_new_lock_file_gets_no_lock_instead_of_an_error(self):
        # Race: both openers saw an empty file; the first already wrote and locked byte 0.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=Path(directory)
            with acquire(root,'lifecycle.lock') as first:
                self.assertTrue(first)
                with patch('src.cycle_lock._is_empty',return_value=True):
                    with acquire(root,'lifecycle.lock') as second:
                        self.assertFalse(second)
            with acquire(root,'lifecycle.lock') as again:
                self.assertTrue(again)


if __name__=='__main__':
    unittest.main()
