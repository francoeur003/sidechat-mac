"""Preserve runtime and third-party copyright notices in installed distributions."""
from pathlib import Path
import sys
import sysconfig
import shutil
import importlib.metadata

destination=Path('dist/SideChat/licenses')
destination.mkdir(parents=True,exist_ok=True)
python_license=Path(sys.base_prefix)/'LICENSE.txt'
if not python_license.exists():python_license=Path(sysconfig.get_path('stdlib'))/'LICENSE.txt'
if not python_license.exists():raise RuntimeError('CPython license missing')
shutil.copy2(python_license,destination/'CPython-LICENSE.txt')
for package in ('pillow','mss','keyring','winsdk','pyinstaller','pywin32-ctypes','numpy'):
    distribution=importlib.metadata.distribution(package)
    found=[]
    for entry in distribution.files or []:
        if any(word in Path(str(entry)).name.lower() for word in ('license','copying','notice')) and '.dist-info/' in str(entry):
            source=distribution.locate_file(entry)
            if source.is_file():
                target=destination/package/str(entry).split('.dist-info/',1)[1]
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target);found.append(target)
    if not found:raise RuntimeError(f'License missing: {package}')
