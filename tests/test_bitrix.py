import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from src import bitrix
from src.live_execution import approve, load

REC={'ready':True,'selected':{'title':'Регулирование доступных скважин','phases':[],'expected_deficit_t':10.6}}
HOOK='https://portal.example/rest/225/secret/'


def project(directory,enabled=True):
    root=Path(directory);(root/'config').mkdir()
    (root/'config/bitrix.json').write_text(json.dumps({'enabled':enabled,'responsible_id':225}),encoding='utf-8')
    return root


def reply(status=200,body=None):
    response=MagicMock(status_code=status,content=b'1');response.json.return_value=body or {'result':{'task':{'id':'731'}}}
    return response


class BitrixTests(unittest.TestCase):
    def setUp(self):
        patcher=patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'petex','BITRIX_WEBHOOK_URL':HOOK});patcher.start();self.addCleanup(patcher.stop)

    def test_one_task_per_approved_plan_without_production_numbers(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch('requests.post',return_value=reply()) as post:
            root=project(directory)
            approve(root,['INC-1'],6,'key',REC,True);approve(root,['INC-1'],6,'key',REC,True)
            post.assert_called_once()
            self.assertTrue(post.call_args.args[0].endswith('/tasks.task.add.json'))
            fields=post.call_args.kwargs['json']['fields']
            self.assertEqual(fields['RESPONSIBLE_ID'],225)
            self.assertNotIn('10.6',fields['TITLE']+fields['DESCRIPTION'])
            self.assertEqual(load(root)['actions'][0]['external']['task_id'],'731')

    def test_no_task_without_approval_disabled_or_in_stub_mode(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch('requests.post') as post:
            root=project(directory)
            with self.assertRaises(ValueError):approve(root,['INC-1'],6,'key',REC)
            with patch.dict(os.environ,{'AGENT_TOOL_BACKEND':'stub'}):approve(root,['INC-1'],6,'key',REC,True)
            self.assertEqual(load(root)['actions'][0]['external']['status'],'skipped_stub')
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch('requests.post') as post2:
            approve(project(directory,enabled=False),['INC-1'],6,'key',REC,True)
        post.assert_not_called();post2.assert_not_called()

    def test_failure_keeps_approval_hides_webhook_and_retries(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root=project(directory)
            with patch('requests.post',side_effect=ConnectionError(f'cannot reach {HOOK}')):approve(root,['INC-1'],6,'key',REC,True)
            external=load(root)['actions'][0]['external']
            self.assertEqual(external['status'],'error');self.assertNotIn('secret',external['error'])
            with patch('requests.post',return_value=reply()):approve(root,['INC-1'],6,'key',REC,True)
            self.assertEqual(len(load(root)['actions']),1)
            self.assertEqual(load(root)['actions'][0]['external']['status'],'created')


if __name__=='__main__':
    unittest.main()
