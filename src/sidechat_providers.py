"""Public distribution provider configuration, isolated from developer credentials."""
import json
import os
import threading
import urllib.error
from pathlib import Path

CONFIG_DIR=Path.home()/'Library/Application Support/SideChat'
CONFIG_FILE=CONFIG_DIR/'settings.json'
PROVIDERS={
    'openai': {'label':'GPT / OpenAI','base':'https://api.openai.com/v1','model':'gpt-4.1-mini'},
    'deepseek': {'label':'DeepSeek','base':'https://api.deepseek.com','model':'deepseek-flash'},
}
DEFAULTS={'provider':'deepseek','models':{k:v['model'] for k,v in PROVIDERS.items()},
          'consent':False,'tones':['高情商话术','贴吧老哥 v1.0','不用']}
_cache={}
_lock=threading.RLock()

def load_settings():
    defaults=json.loads(json.dumps(DEFAULTS))
    try: data=json.loads(CONFIG_FILE.read_text())
    except (OSError,ValueError): return defaults
    if data.get('provider') in PROVIDERS: defaults['provider']=data['provider']
    defaults['consent']=data.get('consent') is True
    for p in PROVIDERS:
        model=data.get('models',{}).get(p)
        if isinstance(model,str) and model.strip() and len(model)<100: defaults['models'][p]=model.strip()
    if isinstance(data.get('tones'),list) and all(isinstance(s,str) for s in data['tones']):
        defaults['tones']=data['tones'][:3]
    return defaults

def write_settings(data):
    # Explicit whitelist: never serialize credentials or arbitrary fields.
    if data['provider'] not in PROVIDERS: raise ValueError('请选择有效接口')
    clean={'provider':data['provider'],'models':{p:data['models'][p].strip() for p in PROVIDERS},
           'consent':data.get('consent') is True,'tones':data.get('tones',DEFAULTS['tones'])[:3]}
    if any(not m or len(m)>100 for m in clean['models'].values()): raise ValueError('请填写模型名称')
    CONFIG_DIR.mkdir(parents=True,exist_ok=True)
    tmp=CONFIG_FILE.with_suffix('.tmp');tmp.write_text(json.dumps(clean,ensure_ascii=False,indent=2))
    os.chmod(tmp,0o600);tmp.replace(CONFIG_FILE)

def get_key(provider):
    import sidechat_keychain
    with _lock:
        if provider not in _cache: _cache[provider]=sidechat_keychain.read(provider)
        return _cache[provider]

def set_key(provider,key):
    import sidechat_keychain
    sidechat_keychain.save(provider,key)
    with _lock: _cache[provider]=key

def credentials():
    settings=load_settings(); p=settings['provider']; config=PROVIDERS[p]
    key=get_key(p) if settings['consent'] else ''
    return config['base'],key,settings['models'][p],'macOS 钥匙串','openai'

def safe_error(exc):
    if isinstance(exc,urllib.error.HTTPError):
        messages={401:'Key 无效或已过期',403:'接口访问被拒绝',402:'账户余额不足',429:'请求过多或额度不足'}
        return f"{messages.get(exc.code,'接口请求失败')}（HTTP {exc.code}）"
    if isinstance(exc,(TimeoutError,urllib.error.URLError)): return '网络连接失败或超时，请稍后重试'
    return '操作失败，请检查接口设置或钥匙串权限'

def chat_json(prompt,system,max_tokens=700,provider=None,key=None,model=None):
    from generate import http_post_json,_endpoint
    settings=load_settings(); p=provider or settings['provider']
    if p not in PROVIDERS: raise ValueError('Unknown provider')
    if key is None:
        if not settings['consent']: raise ValueError('请先在设置页同意使用所选接口')
        key=get_key(p)
    if not key: raise ValueError('请填写 API Key')
    body={'model':model or settings['models'][p], 'max_tokens':max_tokens,
          'messages':[{'role':'system','content':system},{'role':'user','content':prompt}],
          'response_format':{'type':'json_object'}}
    if p=='deepseek': body['thinking']={'type':'disabled'}
    data=http_post_json(_endpoint(PROVIDERS[p]['base'],'openai'),
        {'content-type':'application/json','authorization':'Bearer '+key},body,25)
    raw=data['choices'][0]['message']['content']
    result=json.loads(raw)
    if not isinstance(result,dict): raise ValueError('Expected JSON object')
    return result

def test_connection(provider,key,model):
    result=chat_json('连接测试，请返回 {"ok":true}',
        '这是连接测试，仅返回一个 JSON 对象。',60,provider,key,model)
    if result.get('ok') is not True: raise ValueError('连接测试未返回预期结果')
    return '连接成功 · '+PROVIDERS[provider]['label']
