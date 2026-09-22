"""Two-key onboarding. Connection checks finish before enabling screen analysis."""
import threading
import AppKit as A
import objc
from Foundation import NSObject,NSMakeRect
import sidechat_providers as providers
import sidechat_brand as brand

class SettingsController(NSObject):
    def initWithOwner_(self,owner):
        self=objc.super(SettingsController,self).init()
        if self is None:return None
        self.owner=owner;self.fields={};self.connecting=False
        self.window=A.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(100,100,420,432),A.NSWindowStyleMaskTitled|A.NSWindowStyleMaskClosable,A.NSBackingStoreBuffered,False)
        self.window.setTitle_(brand.NAME);self.window.setReleasedWhenClosed_(False)
        self.window.setAppearance_(A.NSAppearance.appearanceNamed_(A.NSAppearanceNameAqua))
        self.window.setBackgroundColor_(A.NSColor.colorWithCalibratedWhite_alpha_(.98,1))
        self.label('连接你的接口',24,24,372,30,22,True,True)
        self.label('只需填写一次，下次打开直接使用',24,60,372,20,12,center=True)
        for p,title,helper,y in [('jev','Jev API Key','用于意图判断',96),('deepseek','DeepSeek API Key','用于生成回复',186)]:
            self.label(title,24,y,372,20,13,True)
            self.label(helper,24,y+22,372,18,11)
            field=A.NSSecureTextField.alloc().initWithFrame_(self.rect(24,y+44,372,32))
            field.setPlaceholderString_('粘贴 API Key');self.window.contentView().addSubview_(field);self.fields[p]=field
        self.label('点击后，聊天文字将发送至 Jev 和 DeepSeek。\nKey 保存在本机钥匙串，截图留在本机。',24,280,372,40,11,center=True)
        self.status=self.label('',24,320,372,24,11,center=True)
        self.connect=A.NSButton.alloc().initWithFrame_(self.rect(24,348,372,36))
        self.connect.setTitle_('同意并连接');self.connect.setBezelStyle_(A.NSBezelStyleRounded)
        self.connect.setBordered_(False);self.connect.setWantsLayer_(True)
        self.connect.layer().setBackgroundColor_(A.NSColor.colorWithCalibratedWhite_alpha_(.18,1).CGColor())
        self.connect.layer().setCornerRadius_(6)
        self.connect.setContentTintColor_(A.NSColor.whiteColor())
        self.connect.setKeyEquivalent_('\r');self.connect.setTarget_(self);self.connect.setAction_('connect:')
        self.window.contentView().addSubview_(self.connect)
        self.label('首次需允许屏幕录制；填入时需辅助功能。',24,396,372,20,11,center=True)
        return self
    @objc.python_method
    def rect(self,x,y,w,h):return NSMakeRect(x,432-y-h,w,h)
    @objc.python_method
    def label(self,text,x,y,w,h,size=12,bold=False,center=False):
        field=A.NSTextField.labelWithString_(text);field.setFrame_(self.rect(x,y,w,h));field.cell().setWraps_(True)
        field.setFont_(A.NSFont.boldSystemFontOfSize_(size) if bold else A.NSFont.systemFontOfSize_(size))
        if center:field.setAlignment_(A.NSTextAlignmentCenter)
        self.window.contentView().addSubview_(field);return field
    @objc.python_method
    def show(self):
        if not self.connecting:
            for p,field in self.fields.items():
                field.setStringValue_('')
                # Do not block the main/UI thread on a macOS Keychain permission prompt.
                field.setPlaceholderString_('粘贴 API Key；已保存可留空')
            self.status.setStringValue_('')
        self.window.center();self.window.makeKeyAndOrderFront_(None)
        A.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    def connect_(self,sender):
        if self.connecting:return
        entered={p:str(f.stringValue()).strip() for p,f in self.fields.items()}
        for p,title in [('jev','Jev'),('deepseek','DeepSeek')]:
            if any(c.isspace() for c in entered[p]):self.status.setStringValue_(title+' Key 不能包含空白');return
        self.connecting=True;self.connect.setEnabled_(False);self.connect.setTitle_('正在连接…')
        for f in self.fields.values():f.setEnabled_(False)
        self.status.setStringValue_('读取钥匙串中…系统提示时请点允许')
        self.owner._paused=True;self.owner._advance_session(clear_panel=True)
        def work():
            try:
                keys={p:entered[p] or providers.get_key(p) for p in ('jev','deepseek')}
                missing=next((p for p in keys if not keys[p]),None)
                if missing:
                    self.performSelectorOnMainThread_withObject_waitUntilDone_('connected:',
                        {'ok':False,'message':'请填写 '+('Jev' if missing=='jev' else 'DeepSeek')+' API Key'},False)
                    return
                self.performSelectorOnMainThread_withObject_waitUntilDone_('connectProgress:',
                    '正在测试两个接口…（少量 API 用量）',False)
                providers.test_pair(keys)
                for p,key in keys.items():providers.set_key(p,key)
                providers.write_settings({'consent':True})
                result={'ok':True,'message':'两个接口连接成功'}
            except Exception as exc:
                message=str(exc) if isinstance(exc,RuntimeError) and str(exc).startswith(('Jev：','DeepSeek：')) else providers.safe_error(exc)
                result={'ok':False,'message':message}
            self.performSelectorOnMainThread_withObject_waitUntilDone_('connected:',result,False)
        threading.Thread(target=work,daemon=True).start()
    def connectProgress_(self,message):self.status.setStringValue_(message)
    def connected_(self,result):
        self.connecting=False;self.connect.setEnabled_(True);self.connect.setTitle_('同意并连接')
        for f in self.fields.values():f.setEnabled_(True)
        self.status.setStringValue_(result['message'])
        if result['ok']:
            for f in self.fields.values():f.setStringValue_('')
            self.owner.settingsSaved_(None);self.window.orderOut_(None)
        else:self.owner._render('status','接口未连接，请在设置中重试')
