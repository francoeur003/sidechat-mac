import os,sys,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import sidechat_providers as p
from sidechat_judge import CloudJudge,finite_number
import generate,userconfig

class DistributionTests(unittest.TestCase):
    def test_public_mode_cannot_load_developer_env(self):
        with patch.dict(os.environ,{'SIDECHAT_MODE':'1'}),patch('userconfig._merged_env_file',side_effect=AssertionError('must not read')):
            self.assertEqual(userconfig.load(),{})
            self.assertEqual(userconfig.get('TYPESAFE_API_KEY'),'')
    def test_settings_never_serialize_supplied_secret_fields(self):
        with tempfile.TemporaryDirectory() as d,patch.object(p,'CONFIG_DIR',Path(d)),patch.object(p,'CONFIG_FILE',Path(d)/'settings.json'):
            data=json.loads(json.dumps(p.DEFAULTS));data['api_key']='synthetic-test-secret';data['extra']='not allowed'
            p.write_settings(data)
            raw=p.CONFIG_FILE.read_text();self.assertNotIn('synthetic-test-secret',raw);self.assertNotIn('extra',raw)
            self.assertEqual(p.load_settings()['provider'],'deepseek')
    def test_provider_switch_never_mixes_keys_or_hosts(self):
        for provider in p.PROVIDERS:
            settings=json.loads(json.dumps(p.DEFAULTS));settings.update(provider=provider,consent=True)
            with patch.object(p,'load_settings',return_value=settings),patch.object(p,'get_key',side_effect=lambda name:'test-'+name):
                base,key,model,*_=p.credentials()
                self.assertEqual(base,p.PROVIDERS[provider]['base']);self.assertEqual(key,'test-'+provider)
    def test_no_consent_yields_no_generation_credential(self):
        with patch.object(p,'load_settings',return_value=p.DEFAULTS),patch.object(p,'get_key',side_effect=AssertionError('no consent')):
            self.assertEqual(p.credentials()[1],'')
    def test_json_request_deepseek_disables_thinking(self):
        for provider in p.PROVIDERS:
            with patch('generate.http_post_json',return_value={'choices':[{'message':{'content':'{"ok":true}'}}]}) as post:
                self.assertEqual(p.test_connection(provider,'synthetic-test-key','test-model'),'连接成功 · '+p.PROVIDERS[provider]['label'])
                body=post.call_args.args[2]
                self.assertEqual('thinking' in body,provider=='deepseek')
                self.assertEqual(body['model'],'test-model')
    def test_judge_rejects_invalid_model_outputs(self):
        with patch.object(p,'chat_json',return_value={'intent':'unknown','risk':0,'confidence':1}):
            with self.assertRaises(ValueError):CloudJudge().judge('hello')
        with self.assertRaises(ValueError):finite_number(float('nan'),0,1)
        with patch.object(p,'chat_json',return_value={'scores':[.1]}):
            with self.assertRaises(ValueError):CloudJudge().rank_candidates('hello','闲聊',['a','b'])
    def test_errors_do_not_echo_provider_response(self):
        import urllib.error,io
        error=urllib.error.HTTPError('https://api.deepseek.com',401,'secret body',{},io.BytesIO(b'private response'))
        result=p.safe_error(error)
        self.assertIn('401',result);self.assertNotIn('secret',result);self.assertNotIn('private',result)

if __name__=='__main__':unittest.main()
