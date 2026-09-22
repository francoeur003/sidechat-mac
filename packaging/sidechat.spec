# Build with packaging/build_sidechat.sh. Contains only application code and licenses.
from pathlib import Path
import importlib.metadata
import sysconfig
root=Path(SPECPATH).parent
licenses=[(str(root/'LICENSE'),'.'),(str(root/'NOTICE.md'),'.')]
licenses.append((str(Path(sysconfig.get_path('stdlib'))/'LICENSE.txt'),'licenses/CPython'))
for package in ('pyobjc-framework-Cocoa','pyobjc-framework-Quartz','pyobjc-framework-CoreText','pyinstaller'):
    distribution=importlib.metadata.distribution(package)
    for entry in distribution.files or []:
        if '.dist-info/licenses/' in str(entry):
            licenses.append((str(distribution.locate_file(entry)),f'licenses/{package}'))
a=Analysis([str(root/'src/sidechat_app.py')],pathex=[str(root/'src')],binaries=[],datas=licenses,
    hiddenimports=['Vision','Quartz','ApplicationServices','AppKit','sidechat_judge','sidechat_keychain','region_picker'],
    excludes=['torch','transformers','laya','huggingface_hub','pytest','tkinter'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='SideChat',debug=False,bootloader_ignore_signals=False,
        strip=False,upx=False,console=False,target_arch='arm64',codesign_identity=None,entitlements_file=None)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='SideChat')
app=BUNDLE(coll,name='SideChat.app',icon=str(root/'assets/SideChat.icns'),bundle_identifier='com.francoeur.sidechat',
    info_plist={'CFBundleName':'侧语 SideChat','CFBundleDisplayName':'侧语 SideChat',
        'CFBundleShortVersionString':'0.1.0','CFBundleVersion':'1','LSMinimumSystemVersion':'14.0',
        'NSHighResolutionCapable':True,
        'NSScreenCaptureUsageDescription':'侧语读取选定微信窗口，在本机识别文字；经同意后发送文字给所选模型接口。',
        'NSAppleEventsUsageDescription':'侧语可将选中的候选文字填入微信输入框，不会自动发送。'})
