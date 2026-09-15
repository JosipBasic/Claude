# PyInstaller spec for AD Manager.
#
# Must be built ON Windows (PyInstaller does not cross-compile):
#   pip install -r requirements-build.txt
#   pyinstaller adman.spec
#
# Output: dist/adman/adman.exe (plus its supporting files in dist/adman/).
from PyInstaller.utils.hooks import collect_all

datas = [
    ("app/templates", "app/templates"),
    ("app/static", "app/static"),
]
binaries = []
hiddenimports = []

# ldap3/pyasn1 rely on some dynamic imports that PyInstaller's static
# analysis can miss; pull in everything from both packages to be safe.
for pkg in ("ldap3", "pyasn1"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="adman",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="adman",
)
