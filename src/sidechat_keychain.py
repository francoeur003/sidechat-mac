"""macOS Keychain access. Secrets never appear in subprocess arguments or files."""
import ctypes as C

CF = C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
SEC = C.CDLL('/System/Library/Frameworks/Security.framework/Security')
P = C.c_void_p
CF.CFStringCreateWithCString.argtypes = [P, C.c_char_p, C.c_uint32]
CF.CFStringCreateWithCString.restype = P
CF.CFDataCreate.argtypes = [P, C.c_char_p, C.c_long]
CF.CFDataCreate.restype = P
CF.CFDictionaryCreate.argtypes = [P,P,P,C.c_long,P,P]
CF.CFDictionaryCreate.restype = P
CF.CFDataGetLength.argtypes = [P]; CF.CFDataGetLength.restype = C.c_long
CF.CFDataGetBytePtr.argtypes = [P]; CF.CFDataGetBytePtr.restype = P
CF.CFRelease.argtypes = [P]
SEC.SecItemCopyMatching.argtypes = [P,C.POINTER(P)]; SEC.SecItemCopyMatching.restype = C.c_int
SEC.SecItemAdd.argtypes = [P,C.POINTER(P)]; SEC.SecItemAdd.restype = C.c_int
SEC.SecItemUpdate.argtypes = [P,P]; SEC.SecItemUpdate.restype = C.c_int

def constant(name):
    return P.in_dll(SEC if name.startswith('kSec') else CF,name).value

def string(value):
    return CF.CFStringCreateWithCString(None,value.encode(),0x08000100)

def dictionary(pairs):
    keys=(P*len(pairs))(*(constant(k) for k,v in pairs))
    vals=(P*len(pairs))(*(v for k,v in pairs))
    return CF.CFDictionaryCreate(None,keys,vals,len(pairs),
        C.addressof(C.c_byte.in_dll(CF,'kCFTypeDictionaryKeyCallBacks')),
        C.addressof(C.c_byte.in_dll(CF,'kCFTypeDictionaryValueCallBacks')))

def _query(provider):
    if provider not in ('openai','deepseek','test'): raise ValueError('Unknown provider')
    service=string('com.francoeur.sidechat.'+provider)
    account=string('api-key')
    q=dictionary([('kSecClass',constant('kSecClassGenericPassword')),
                  ('kSecAttrService',service),('kSecAttrAccount',account)])
    CF.CFRelease(service); CF.CFRelease(account)
    return q

def read(provider):
    q=_query(provider)
    # Add return-data flag by constructing the entire query; dictionaries are immutable.
    CF.CFRelease(q)
    service=string('com.francoeur.sidechat.'+provider); account=string('api-key')
    q=dictionary([('kSecClass',constant('kSecClassGenericPassword')),
        ('kSecAttrService',service),('kSecAttrAccount',account),
        ('kSecReturnData',constant('kCFBooleanTrue'))])
    out=P()
    try:
        status=SEC.SecItemCopyMatching(q,C.byref(out))
        if status==-25300: return ''
        if status!=0: raise RuntimeError(f'钥匙串读取失败（{status}）')
        return C.string_at(CF.CFDataGetBytePtr(out),CF.CFDataGetLength(out)).decode()
    finally:
        for v in (q,service,account,out.value):
            if v: CF.CFRelease(v)

def save(provider,key):
    if not isinstance(key,str) or not key.strip() or any(c.isspace() for c in key):
        raise ValueError('API Key 不能为空或包含空白')
    q=_query(provider); raw=key.encode(); data=CF.CFDataCreate(None,raw,len(raw))
    updates=dictionary([('kSecValueData',data)])
    try:
        status=SEC.SecItemUpdate(q,updates)
        if status==-25300:
            service=string('com.francoeur.sidechat.'+provider); account=string('api-key')
            add=dictionary([('kSecClass',constant('kSecClassGenericPassword')),
                ('kSecAttrService',service),('kSecAttrAccount',account),('kSecValueData',data)])
            try: status=SEC.SecItemAdd(add,None)
            finally:
                for v in (add,service,account): CF.CFRelease(v)
        if status!=0: raise RuntimeError(f'钥匙串保存失败（{status}）')
    finally:
        for v in (q,data,updates): CF.CFRelease(v)
