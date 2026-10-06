import json
import os
import unittest
from unittest.mock import patch
from src import llm_client, tool_gateway
from src.live_reasoning import SCHEMA


class Response:
    def __init__(self,status,body):self.status_code=status;self._body=body;self.text=json.dumps(body)
    def json(self):return self._body


ANSWER={'assessment':'x','hypotheses':[{'title':f'h{i}','candidate_wells':[],'engineering_rationale':'r','verification':'v','missing_data':[]} for i in range(4)]}


class LlmClientTests(unittest.TestCase):
    def test_provider_selection(self):
        with patch.dict(os.environ,{'AGENT_LLM':'openrouter:openai/gpt-4o-mini'}):
            self.assertEqual(llm_client.provider(),('openrouter','openai/gpt-4o-mini',llm_client.OPENROUTER_URL))
            self.assertEqual(tool_gateway.cache_marker(),{'llm':'openrouter:openai/gpt-4o-mini'})
        with patch.dict(os.environ,{'AGENT_LLM':'lmstudio:qwen@http://server:1234/v1'}):
            self.assertEqual(llm_client.provider(),('lmstudio','qwen','http://server:1234/v1'))
        with patch.dict(os.environ,{'AGENT_LLM':'codex'}):
            self.assertEqual(tool_gateway.cache_marker(),{})

    def test_strict_schema_answer_with_usage_and_cost(self):
        body={'choices':[{'message':{'content':json.dumps(ANSWER)}}],'usage':{'prompt_tokens':1000,'completion_tokens':200,'cost':0.0003}}
        with patch('src.llm_client.requests.post',return_value=Response(200,body)) as post:
            answer,meta=llm_client.ask('prompt',SCHEMA,'m','https://x/v1','key')
        sent=post.call_args.kwargs['json']
        self.assertTrue(sent['response_format']['json_schema']['strict'])
        self.assertNotIn('minItems',json.dumps(sent['response_format']))   # checked locally instead
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'],'Bearer key')
        self.assertEqual((meta['prompt_tokens'],meta['completion_tokens'],meta['cost_usd']),(1000,200,0.0003))
        self.assertEqual(answer,ANSWER)

    def test_dropped_connection_is_an_llm_error_not_petex(self):
        import requests
        from src import license_retry
        reset=requests.ConnectionError("('Connection aborted.', ConnectionResetError(10054, 'reset'))")
        with patch('src.llm_client.requests.post',side_effect=reset), self.assertRaises(RuntimeError) as caught:
            llm_client.ask('prompt',SCHEMA,'gpt-oss','http://server:1234/v1')
        text=license_retry.readable(str(caught.exception))
        self.assertTrue(text.startswith('LLM gpt-oss: сервер LLM недоступен'))
        self.assertNotIn('PetEx',text)

    def test_local_answer_is_streamed_and_assembled(self):
        text=json.dumps(ANSWER)
        events=[{'choices':[{'delta':{'reasoning':'думаю'}}]},{'choices':[{'delta':{'content':''}}]}]+[{'choices':[{'delta':{'content':text[i:i+50]}}]} for i in range(0,len(text),50)]
        events.append({'choices':[],'usage':{'prompt_tokens':900,'completion_tokens':300}})
        lines=[('data: '+json.dumps(e,ensure_ascii=False)).encode('utf-8') for e in events]+[b'',b'data: [DONE]']
        class Stream:
            status_code=200
            def iter_lines(self):return iter(lines)
        with patch('src.llm_client.requests.post',return_value=Stream()) as post:
            answer,meta=llm_client.ask('p',SCHEMA,'gpt-oss','http://server:1234/v1',stream=True)
        self.assertTrue(post.call_args.kwargs['stream']);self.assertTrue(post.call_args.kwargs['json']['stream'])
        self.assertEqual(answer,ANSWER)
        self.assertEqual((meta['prompt_tokens'],meta['completion_tokens']),(900,300))

    def test_too_few_hypotheses_are_rejected_locally(self):
        short=dict(ANSWER,hypotheses=ANSWER['hypotheses'][:2])
        body={'choices':[{'message':{'content':json.dumps(short)}}],'usage':{}}
        with patch('src.llm_client.requests.post',return_value=Response(200,body)):
            with self.assertRaises(ValueError) as caught:llm_client.ask('p',SCHEMA,'m','https://x/v1')
        from src import license_retry
        text=license_retry.readable(str(caught.exception))
        self.assertEqual(text,'LLM m: ответ не прошёл проверку схемы (hypotheses: minItems 4)')

    def test_http_error_is_reported_without_the_key(self):
        with patch('src.llm_client.requests.post',return_value=Response(401,{'error':'bad key'})):
            with self.assertRaises(RuntimeError) as error:llm_client.ask('p',SCHEMA,'m','https://x/v1','secret-key')
        self.assertNotIn('secret-key',str(error.exception))


if __name__=='__main__':
    unittest.main()
