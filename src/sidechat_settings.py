"""Native settings form backed by provider configuration and macOS Keychain."""
import threading
import AppKit as A
import objc
from Foundation import NSObject,NSMakeRect,NSURL
import sidechat_providers as providers
import sidechat_brand as brand
import styles

class SettingsController(NSObject):
    def initWithOwner_(self,owner):
        self=objc.super(SettingsController,self).init()
        if self is None:return None
        self.owner=owner; self.fields={};self.models={};self.buttons=[];self.keys={}
        self.window=A.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(100,100,528,636),A.NSWindowStyleMaskTitled|A.NSWindowStyleMaskClosable,A.NSBackingStoreBuffered,False)
        self.window.setTitle_(brand.NAME+' · 模型与接口')
        self.window.setReleasedWhenClosed_(False)
        self.window.setAppearance_(A.NSAppearance.appearanceNamed_(A.NSAppearanceNameAqua))
        self.window.setBackgroundColor_(A.NSColor.colorWithCalibratedWhite_alpha_(.98,1))
        view=self.window.contentView()
        self.label('模型与接口',24,18,480,28,20,True)
        self.label('任选一个接口即可开始；两个 Key 分开保存。',24,50,480,20,12)
        self.provider=A.NSPopUpButton.alloc().initWithFrame_pullsDown_(self.rect(24,80,240,28),False)
        self.provider.addItemsWithTitles_(['DeepSeek','GPT / OpenAI']);view.addSubview_(self.provider)
        self.label('当前用于意图分析与回复生成',276,85,228,20,11)
        for p,title,y in [('openai','GPT / OpenAI',122),('deepseek','DeepSeek',259)]:
            self.label(title,24,y,240,24,15,True)
            self.label('API Key',24,y+32,70,24,12)
            f=A.NSSecureTextField.alloc().initWithFrame_(self.rect(98,y+29,406,28))
            f.setPlaceholderString_('输入 API Key');view.addSubview_(f);self.fields[p]=f
            self.label('模型',24,y+73,70,24,12)
            m=A.NSTextField.alloc().initWithFrame_(self.rect(98,y+69,406,28));view.addSubview_(m);self.models[p]=m
        self.label('话术（每种生成 2 条）',24,395,480,22,12,True)
        self.tones=[]
        for i in range(3):
            pop=A.NSPopUpButton.alloc().initWithFrame_pullsDown_(self.rect(24+i*162,424,156,28),False)
            pop.addItemsWithTitles_(styles.labels()+[styles.NONE_LABEL]);view.addSubview_(pop);self.tones.append(pop)
        self.consent=A.NSButton.alloc().initWithFrame_(self.rect(24,467,480,24))
        self.consent.setButtonType_(A.NSButtonTypeSwitch)
        self.consent.setTitle_('允许将当前聊天文字发送给所选服务商进行分析和回复')
        self.consent.setFont_(A.NSFont.systemFontOfSize_(11));view.addSubview_(self.consent)
        self.label('Key 仅保存在本机钥匙串。截图留在本机；API 按服务商规则计费。',24,497,480,20,11)
        self.status=self.label('',24,522,480,24,12)
        self.button('测试连接',24,559,100,'test:')
        self.button('保存并使用',384,559,120,'save:')
        self.button('GitHub',24,599,80,'github:')
        link=self.button('作者抖音主页',116,599,124,'douyin:')
        link.setEnabled_(bool(brand.DOUYIN_URL))
        if not brand.DOUYIN_URL:link.setToolTip_('作者尚未提供抖音主页链接')
        self.label('v'+brand.VERSION,432,603,72,20,11)
        return self
    @objc.python_method
    def rect(self,x,y,w,h):return NSMakeRect(x,636-y-h,w,h)
    @objc.python_method
    def label(self,text,x,y,w,h,size=12,bold=False):
        f=A.NSTextField.labelWithString_(text);f.setFrame_(self.rect(x,y,w,h))
        f.setFont_(A.NSFont.boldSystemFontOfSize_(size) if bold else A.NSFont.systemFontOfSize_(size))
        f.setTextColor_(A.NSColor.labelColor());self.window.contentView().addSubview_(f);return f
    @objc.python_method
    def button(self,text,x,y,w,selector):
        b=A.NSButton.alloc().initWithFrame_(self.rect(x,y,w,28));b.setTitle_(text)
        b.setBezelStyle_(A.NSBezelStyleRounded);b.setTarget_(self);b.setAction_(selector)
        self.window.contentView().addSubview_(b);self.buttons.append(b);return b
    @objc.python_method
    def show(self):
        s=providers.load_settings();self.provider.selectItemAtIndex_(0 if s['provider']=='deepseek' else 1)
        for p in providers.PROVIDERS:
            self.fields[p].setStringValue_('');self.models[p].setStringValue_(s['models'][p])
            try:saved=bool(providers.get_key(p))
            except Exception:saved=False
            self.fields[p].setPlaceholderString_('已保存 · 留空保留原 Key' if saved else '输入 API Key')
        for i,pop in enumerate(self.tones):
            value=s['tones'][i] if i<len(s['tones']) else styles.NONE_LABEL
            pop.selectItemWithTitle_(value if value in styles.PRESETS else styles.NONE_LABEL)
        self.consent.setState_(A.NSControlStateValueOn if s['consent'] else A.NSControlStateValueOff)
        self.status.setStringValue_('');self.window.center();self.window.makeKeyAndOrderFront_(None)
        A.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    @objc.python_method
    def selected(self):return 'deepseek' if self.provider.indexOfSelectedItem()==0 else 'openai'
    @objc.python_method
    def snapshot(self):
        return {'provider':self.selected(),'models':{p:str(f.stringValue()).strip() for p,f in self.models.items()},
                'consent':self.consent.state()==A.NSControlStateValueOn,
                'tones':[p.titleOfSelectedItem() for p in self.tones]}
    def save_(self,sender):
        s=self.snapshot()
        if not s['consent']:
            self.status.setStringValue_('请先勾选聊天文字发送授权');return
        if not any(t in styles.PRESETS for t in s['tones']):
            self.status.setStringValue_('请至少选择一种话术');return
        try:
            for p,f in self.fields.items():
                key=str(f.stringValue()).strip()
                if key:providers.set_key(p,key)
            if not providers.get_key(s['provider']):
                self.status.setStringValue_('请填写所选接口的 API Key');return
            providers.write_settings(s)
            for f in self.fields.values():f.setStringValue_('')
            self.owner.settingsSaved_(None)
            self.status.setStringValue_('已保存，助手开始读取微信')
        except Exception as exc:self.status.setStringValue_(providers.safe_error(exc))
    def test_(self,sender):
        p=self.selected();s=self.snapshot()
        try:key=str(self.fields[p].stringValue()).strip() or providers.get_key(p)
        except Exception as exc:self.status.setStringValue_(providers.safe_error(exc));return
        if not key:self.status.setStringValue_('请先填写 API Key');return
        self.status.setStringValue_('正在测试连接…（少量 API 用量）')
        for b in self.buttons:b.setEnabled_(False)
        def work():
            try:status=providers.test_connection(p,key,s['models'][p])
            except Exception as exc:status=providers.safe_error(exc)
            self.performSelectorOnMainThread_withObject_waitUntilDone_('testDone:',status,False)
        threading.Thread(target=work,daemon=True).start()
    def testDone_(self,status):
        self.status.setStringValue_(status)
        for b in self.buttons:b.setEnabled_(True)
        if not brand.DOUYIN_URL:self.buttons[-1].setEnabled_(False)
    def github_(self,sender):A.NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(brand.GITHUB_URL))
    def douyin_(self,sender):
        if brand.DOUYIN_URL:A.NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(brand.DOUYIN_URL))
