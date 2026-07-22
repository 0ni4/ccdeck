# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for cc-home.

Toggle ONEFILE / CONSOLE below. The SDK's bundled claude executable (~235MB) is
intentionally excluded — frozen builds use an installed `claude` CLI (see
server/chat.py:resolve_cli_path).
"""
from PyInstaller.utils.hooks import collect_all

ONEFILE = True
CONSOLE = False

datas = [("web", "web")]
binaries = []
hiddenimports = [
    "server.main", "server.sessions", "server.chat", "server.manage",
    "webview.platforms.winforms", "webview.platforms.edgechromium",
]

for pkg in [
    "uvicorn", "fastapi", "starlette", "pydantic", "pydantic_core",
    "websockets", "anyio", "sniffio", "claude_agent_sdk", "webview",
    "clr_loader", "pythonnet",
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# Drop the SDK's bundled claude executable (~235MB); use an installed CLI instead.
datas = [(s, d) for (s, d) in datas if "_bundled" not in s]
binaries = [(s, d) for (s, d) in binaries if "_bundled" not in s]

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

if ONEFILE:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="cc-home", debug=False, bootloader_ignore_signals=False,
        strip=False, upx=False, runtime_tmpdir=None,
        console=CONSOLE, disable_windowed_traceback=False,
    )
else:
    exe = EXE(
        pyz, a.scripts, [], exclude_binaries=True,
        name="cc-home", debug=False, bootloader_ignore_signals=False,
        strip=False, upx=False, console=CONSOLE,
        disable_windowed_traceback=False,
    )
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="cc-home")
