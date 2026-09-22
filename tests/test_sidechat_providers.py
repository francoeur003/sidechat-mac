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
            p.write_settings({'consent':True,'api_key':'synthetic-test-secret','extra':'not allowed'})
            raw=p.CONFIG_FILE.read_text();self.assertNotIn('synthetic-test-secret',raw);self.assertNotIn('extra',raw)
            self.assertTrue(p.load_settings()['consent'])
    def test_old_single_service_consent_requires_new_opt_in(self):
        with tempfile.TemporaryDirectory() as d,patch.object(p,'CONFIG_FILE',Path(d)/'settings.json'):
            p.CONFIG_FILE.write_text(json.dumps({'consent':True,'provider':'openai'}))
            self.assertFalse(p.load_settings()['consent'])
    def test_fixed_services_never_mix_keys_or_hosts(self):
        with patch.object(p,'load_settings',return_value=dict(p.DEFAULTS,consent=True)),patch.object(p,'get_key',side_effect=lambda name:'test-'+name):
            base,key,model,*_=p.credentials()
            self.assertEqual(base,'https://api.deepseek.com');self.assertEqual(key,'test-deepseek')
            with patch('generate.http_post_json',return_value={'answers':{}}) as post:
                p.jev_evaluate('data',{})
                url,headers,body,_=post.call_args.args
                self.assertEqual(url,'https://api.typesafe.ai/v1/systemone')
                self.assertEqual(headers['authorization'],'Bearer test-jev')
                self.assertEqual(body['model'],'jev-latest')
    def test_no_consent_prevents_both_requests(self):
        with patch.object(p,'load_settings',return_value=p.DEFAULTS),patch.object(p,'get_key',side_effect=AssertionError('no consent')):
            self.assertEqual(p.credentials()[1],'')
            self.assertFalse(p.ready())
            with self.assertRaises(ValueError):p.jev_evaluate('hello',{})
    def test_both_keys_required(self):
        with patch.object(p,'load_settings',return_value=dict(p.DEFAULTS,consent=True)),patch.object(p,'get_key',side_effect=lambda name:'' if name=='jev' else 'synthetic'):
            self.assertFalse(p.ready())
    def test_json_request_deepseek_disables_thinking(self):
        with patch('generate.http_post_json',return_value={'choices':[{'message':{'content':'{"ok":true}'}}]}) as post:
            p.test_connection('deepseek','synthetic-test-key',p.PROVIDERS['deepseek']['model'])
            self.assertEqual(post.call_args.args[2]['thinking'],{'type':'disabled'})
    def test_jev_parser_rejects_invalid_outputs(self):
        with patch.object(p,'jev_evaluate',return_value={'answers':{'intent':{'choice':'unknown'}}}):
            with self.assertRaises(ValueError):CloudJudge().judge('hello')
        with self.assertRaises(ValueError):finite_number(float('nan'),0,1)
        with patch.object(p,'jev_evaluate',return_value={'answers':{'best':{'choice':'reply_0','probabilities':{'reply_0':1}}}}):
            with self.assertRaises(ValueError):CloudJudge().rank_candidates('hello','闲聊',['a','b'])
    def test_duplicate_reply_texts_have_distinct_ranking_ids(self):
        with patch.object(p,'jev_evaluate',return_value={'answers':{'best':{'choice':'reply_0','probabilities':{'reply_0':.7,'reply_1':.3}}}}) as call:
            result=CloudJudge().rank_candidates('hello','闲聊',['a','a'])
            self.assertEqual(len(result),2);self.assertEqual(result[0]['prob'],.7)
            self.assertEqual(len(call.call_args.args[1]['best']['criteria']),2)
    def test_connection_stops_before_deepseek_if_jev_fails(self):
        with patch.object(p,'jev_evaluate',side_effect=TimeoutError),patch.object(p,'test_connection') as deepseek:
            with self.assertRaisesRegex(RuntimeError,'Jev'):p.test_pair({'jev':'a','deepseek':'b'})
            deepseek.assert_not_called()
    def test_errors_do_not_echo_provider_response(self):
        import urllib.error,io
        error=urllib.error.HTTPError('https://api.deepseek.com',401,'secret body',{},io.BytesIO(b'private response'))
        result=p.safe_error(error)
        self.assertIn('401',result);self.assertNotIn('secret',result);self.assertNotIn('private',result)

if __name__=='__main__':unittest.main()
