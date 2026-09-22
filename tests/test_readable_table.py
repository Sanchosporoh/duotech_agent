import unittest
from src.live_dashboard import russian_text


class ReadableTableTests(unittest.TestCase):
    def test_internal_terms_are_explained_in_russian(self):
        result=russian_text('Use opportunities; maximum_change; model control unit')
        self.assertNotIn('opportunities',result)
        self.assertNotIn('maximum_change',result)
        self.assertIn('реестра возможностей',result)
