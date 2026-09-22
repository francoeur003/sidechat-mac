import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from generate import Generator


class DeepSeekTests(unittest.TestCase):
    def test_short_reply_uses_non_thinking_mode(self):
        g=Generator()
        with patch('generate.load_credentials',return_value=(
                'https://api.deepseek.com','unit-test','deepseek-flash','test','openai')), \
             patch.object(g,'_post',return_value={'choices':[{'message':{'content':'收到'}}]}) as post:
            self.assertEqual(g._call('请简短回复'),'收到')
            self.assertEqual(post.call_args.args[2]['thinking'],{'type':'disabled'})

    def test_other_provider_payload_is_unchanged(self):
        g=Generator()
        with patch('generate.load_credentials',return_value=(
                'https://example.com/v1','unit-test','test-model','test','openai')), \
             patch.object(g,'_post',return_value={'choices':[{'message':{'content':'收到'}}]}) as post:
            g._call('请简短回复')
            self.assertNotIn('thinking',post.call_args.args[2])


if __name__=='__main__':
    unittest.main()
