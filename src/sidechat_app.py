"""SideChat distributable entry point: small native HUD, embedded runtime, own config."""
import os
os.environ['SIDECHAT_MODE']='1'
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import threading
import AppKit as A
import objc
from Foundation import NSMakeRect,NSMakeSize,NSTimer,NSURL
import hud
from hud import HudController,PALETTE
import styles
import sidechat_brand as brand
import sidechat_providers as providers
from sidechat_settings import SettingsController

class SideChatController(HudController):
    @objc.python_method
    def _build_panel(self):
        self.more=False; self.settings_controller=None;self.region_uncertain=False
        self._credentials_ready=False;self._checking_credentials=False
        saved=providers.load_settings()['tones']
        self.slot_tones=[t if t in styles.PRESETS else styles.NONE_LABEL for t in saved]
        self.slot_tones=(self.slot_tones+[styles.NONE_LABEL]*3)[:3]
        style=A.NSWindowStyleMaskTitled|A.NSWindowStyleMaskClosable|A.NSWindowStyleMaskMiniaturizable|A.NSWindowStyleMaskNonactivatingPanel
        self.panel=A.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(NSMakeRect(0,0,240,144),style,A.NSBackingStoreBuffered,False)
        self.panel.setTitle_(brand.NAME);self.panel.setLevel_(A.NSFloatingWindowLevel)
        self.panel.setHidesOnDeactivate_(False);self.panel.setBecomesKeyOnlyIfNeeded_(True)
        self.panel.setAppearance_(A.NSAppearance.appearanceNamed_(A.NSAppearanceNameAqua))
        self.panel.setBackgroundColor_(PALETTE['bg']);self.panel.setReleasedWhenClosed_(False)
        view=A.NSView.alloc().initWithFrame_(NSMakeRect(0,0,240,144));self.panel.setContentView_(view)
        self._title_h=self.panel.frame().size.height-144
        self.rows={}
        for key,size in [('chat',12),('status',11),('message',14),('sender',11),('intent',12),('confidence',11),('risk',11),('actions',11),('cand_header',11)]:
            tf=self._make_label(0,0,216,20,size=size,color=PALETTE['text'] if key in ['message','intent'] else PALETTE['muted'],bold=key=='chat')
            tf.cell().setWraps_(True);view.addSubview_(tf);self.rows[key]=tf
        self.settings_button=self._make_button(0,0,48,24,'设置','settings:',0);view.addSubview_(self.settings_button)
        self.more_button=self._make_button(0,0,216,24,'更多候选与话术','more:',0);view.addSubview_(self.more_button)
        self.author_button=self._make_button(0,0,216,24,'作者抖音主页 ↗' if brand.DOUYIN_URL else '项目主页 ↗','author:',0);view.addSubview_(self.author_button)
        self.region_button=self._make_button(0,0,76,24,'调整范围','pickChatRegion:',0);view.addSubview_(self.region_button)
        self._tone_labels=[]
        for slot in range(styles.MAX_SLOTS):
            label=self._make_label(0,0,216,20,size=11,color=PALETTE['muted'],bold=True)
            view.addSubview_(label);self._tone_labels.append(label)
            self._rows.append([])
            for row in range(styles.PER_TONE):
                tag=slot*styles.PER_TONE+row
                controls={'prob':self._make_label(0,0,70,16,size=11,color=PALETTE['muted']),
                    'text':self._make_label(0,0,216,40,size=12,color=PALETTE['text']),
                    'btn':self._make_button(0,0,40,24,'复制','copyCandidate:',tag),
                    'fill_btn':self._make_button(0,0,40,24,'填入','fillCandidate:',tag)}
                controls['text'].cell().setWraps_(True)
                for c in controls.values():view.addSubview_(c)
                self._rows[slot].append(controls)
        self._wire_window_controls();self._install_status_item()
        self.panel.standardWindowButton_(A.NSWindowCloseButton).setToolTip_('退出侧语 SideChat')
        self.rows['chat'].setStringValue_('打开一个微信对话')
        self.rows['status'].setStringValue_('聊天区域会自动识别\n无需手动框选');self._relayout()
    @objc.python_method
    def _install_status_item(self):
        objc.super(SideChatController,self)._install_status_item()
        self.status_item.button().setTitle_('语');self.status_item.button().setToolTip_(brand.NAME)
        menu=self.status_item.menu()
        for existing in menu.itemArray():
            if str(existing.title())=='退出 jev-jarvis':existing.setTitle_('退出侧语 SideChat')
            if str(existing.title())=='框选聊天区域…':existing.setTitle_('识别不准？调整范围…')
        item=A.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('模型与接口…','settings:',',');item.setTarget_(self);menu.insertItem_atIndex_(item,0)
    @objc.python_method
    def _relayout(self):
        if not hasattr(self,'rows') or not hasattr(self,'_tone_labels'):return
        placements=[]
        def put(c,x,y,w,h):
            c.setHidden_(False);placements.append((c,x,y,w,h))
        for c in list(self.rows.values())+self._tone_labels+[self.settings_button,self.more_button,self.author_button,self.region_button]:c.setHidden_(True)
        for group in self._rows:
            for row in group:
                for c in row.values():c.setHidden_(True)
        put(self.rows['chat'],12,10,158,18);put(self.settings_button,178,7,50,24)
        put(self.rows['status'],12,34,216,30)
        if self._collapsed:
            height=72
        else:
            y=68
            if str(self.rows['message'].stringValue()).strip():
                put(self.rows['message'],12,y,216,40);y+=44
                put(self.rows['sender'],12,y,216,16);y+=20
            if str(self.rows['intent'].stringValue()).strip() not in ('','—'):
                put(self.rows['intent'],12,y,44,18);put(self.rows['confidence'],58,y,94,18);put(self.rows['risk'],158,y,70,18);y+=24
            active=[i for i in range(3) if self._slot_active(i)]
            shown=active if self.more else active[:1]
            for slot in shown:
                live=[row for row in range(2) if self.cand_texts[slot*2+row]]
                if not live:continue
                self._tone_labels[slot].setStringValue_(self.slot_tones[slot]);put(self._tone_labels[slot],12,y,216,18);y+=22
                for row in live:
                    r=self._rows[slot][row]
                    put(r['text'],12,y,216,40);put(r['prob'],12,y+43,100,16)
                    put(r['btn'],136,y+40,42,24);put(r['fill_btn'],184,y+40,44,24);y+=72
            if any(self.cand_texts):
                self.more_button.setTitle_('收起更多候选' if self.more else '更多候选与话术 ⌄')
                put(self.more_button,12,y,216,24);y+=28
            elif self.region_uncertain:
                put(self.region_button,12,y,84,24);y+=28
            if any(self.cand_texts):
                put(self.author_button,12,y,216,24);y+=28
            height=max(136,y+8)
        view=self.panel.contentView();view.setFrameSize_(NSMakeSize(240,height))
        for c,x,y,w,h in placements:c.setFrame_(NSMakeRect(x,height-y-h,w,h))
        frame=self.panel.frame();top=frame.origin.y+frame.size.height
        self.panel.setFrame_display_(NSMakeRect(frame.origin.x,top-height-self._title_h,240,height+self._title_h),True)
        self._expanded_h=height+self._title_h;self._last_origin=None
    @objc.python_method
    def _render(self,key,text,color=None):
        if key=='confidence':text=text.replace('意图识别率','估计 ')
        objc.super(SideChatController,self)._render(key,text,color);self._relayout()
    @objc.python_method
    def _clear_candidates(self):
        objc.super(SideChatController,self)._clear_candidates();self._relayout()
    def applyIncoming_(self,payload):
        self.region_uncertain=False
        objc.super(SideChatController,self).applyIncoming_(payload);self._relayout()
    def applyReset_(self,title):objc.super(SideChatController,self).applyReset_(title);self._relayout()
    def applyStreamLine_(self,payload):objc.super(SideChatController,self).applyStreamLine_(payload);self._relayout()
    def collapsePanel_(self,sender):self._collapsed=not self._collapsed;self._relayout()
    def more_(self,sender):self.more=not self.more;self._relayout()
    def settings_(self,sender):
        if self.settings_controller is None:self.settings_controller=SettingsController.alloc().initWithOwner_(self)
        self.settings_controller.show()
    def author_(self,sender):A.NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(brand.DOUYIN_URL or brand.GITHUB_URL))
    def settingsSaved_(self,sender):
        self._paused=True;self._advance_session(clear_panel=True)
        from generate import Generator
        self.generator=Generator()
        self._credentials_ready=True
        self.slot_tones=providers.load_settings()['tones'];self._fingerprint=None;self._last_full=None
        self._context_id=None;self._latest_turn=None;self.last_seen=None;self._next_read_ts=0
        self._paused=False;self.pause_item.setTitle_('暂停读屏')
        self._render('status','接口已连接 · 正在自动识别微信')
    def tick_(self,timer):
        if not providers.load_settings()['consent']:
            self._render('status','请在设置中填写两个 Key\n点击「同意并连接」');return
        if not self._credentials_ready:
            if not self._checking_credentials:
                self._checking_credentials=True
                self._render('status','正在读取本机钥匙串…')
                def check():
                    try:ready=bool(providers.ready())
                    except Exception:ready=False
                    self.performSelectorOnMainThread_withObject_waitUntilDone_('credentialsChecked:',ready,False)
                threading.Thread(target=check,daemon=True).start()
            return
        objc.super(SideChatController,self).tick_(timer)
    def credentialsChecked_(self,ready):
        self._credentials_ready=bool(ready)
        if not ready:
            self._render('status','无法读取 Key，请在设置中重新连接')
            self.settings_(None)
    def applyError_(self,text):
        self.region_uncertain=any(s in text for s in ('聊天区域','聊天标题','框选'))
        if 'HTTP' in text or 'Error' in text:text='分析失败，请检查接口设置或连接'
        objc.super(SideChatController,self).applyError_(text);self._relayout()
    def applyHidden_(self,reason):
        self._fingerprint=None;self._last_full=None;self._win_wid=None;self.wechat_win=None
        self.region_uncertain=False;self.applyReset_('打开一个微信对话')
        self._render('status','聊天区域会自动识别\n等待聊天窗口…',PALETTE['muted'])
        self._ov_panel.orderOut_(None);self._show();self._relayout()

def main():
    app=A.NSApplication.sharedApplication();app.setActivationPolicy_(A.NSApplicationActivationPolicyRegular)
    # Single instance: prevents duplicate API calls and competing floating windows.
    if len(A.NSRunningApplication.runningApplicationsWithBundleIdentifier_(brand.BUNDLE_ID))>1:return
    controller=SideChatController.alloc().init();controller._show();controller.panel.center()
    timer=NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(.25,controller,'tick:',None,True)
    A.NSRunLoop.currentRunLoop().addTimer_forMode_(timer,A.NSDefaultRunLoopMode)
    if not providers.load_settings()['consent']:controller.settings_(None)
    threading.Thread(target=controller._warm,daemon=True).start()
    app.run()

if __name__=='__main__':main()
