import unittest
from unittest.mock import patch,Mock
import sidechat_secrets
from sidechat_windows import validate_message

class WindowsTests(unittest.TestCase):
    def test_blank_and_oversized_messages_are_rejected(self):
        for message in ('  ', 'a'*6001):
            with self.assertRaises(ValueError):validate_message(message)
        self.assertEqual(validate_message(' hello '),'hello')

    def test_windows_keys_use_only_os_credential_store(self):
        store=Mock();store.get_password.return_value='synthetic'
        with patch.object(sidechat_secrets.sys,'platform','win32'),patch.object(sidechat_secrets,'backend',return_value=store):
            sidechat_secrets.save('jev','synthetic')
            self.assertEqual(sidechat_secrets.read('jev'),'synthetic')
        store.set_password.assert_called_once_with('com.francoeur.sidechat.jev','api-key','synthetic')

    def test_invalid_provider_and_key_are_rejected(self):
        with self.assertRaises(ValueError):sidechat_secrets.read('unknown')
        for key in ('', 'a b'):
            with self.assertRaises(ValueError):sidechat_secrets.save('jev',key)

    def test_credential_failure_does_not_fall_back_to_plaintext(self):
        with patch.object(sidechat_secrets,'backend',side_effect=RuntimeError('store unavailable')):
            with self.assertRaises(RuntimeError):sidechat_secrets.save('jev','synthetic')

if __name__=='__main__':unittest.main()
