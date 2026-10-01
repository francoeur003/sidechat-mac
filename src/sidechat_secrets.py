"""Only native OS credential stores are allowed; no plaintext fallback."""
import sys

def backend():
    if sys.platform == 'win32':
        from keyring.backends.Windows import WinVaultKeyring
        return WinVaultKeyring()
    if sys.platform == 'darwin':
        import sidechat_keychain
        return sidechat_keychain
    raise RuntimeError('Unsupported credential store')

def validate(provider):
    if provider not in ('jev', 'deepseek', 'openai', 'test'):
        raise ValueError('Unknown provider')

def read(provider):
    validate(provider)
    store = backend()
    if sys.platform == 'win32':
        return store.get_password('com.francoeur.sidechat.' + provider, 'api-key') or ''
    return store.read(provider)

def save(provider, key):
    validate(provider)
    if not isinstance(key,str) or not key or any(c.isspace() for c in key):
        raise ValueError('API Key 不能为空或包含空白')
    store = backend()
    if sys.platform == 'win32':
        store.set_password('com.francoeur.sidechat.' + provider, 'api-key', key)
    else:
        store.save(provider,key)
