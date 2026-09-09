# PyInstaller spec — one-folder build with bundled dashboard + prompts.
import pathlib

root = pathlib.Path(SPECPATH).resolve()
datas = [
    (str(root / "dashboard" / "dist"), "dashboard/dist"),
    (str(root / "sparks" / "prompts"), "sparks/prompts"),
    (str(root / "settings.yaml"), "."),
    (str(root / "sources.yaml"), "."),
]
hiddenimports = [
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "apscheduler.schedulers.background", "pystray._win32",
    "ddgs", "primp",
]
a = Analysis(["sparks/app/launch.py"], pathex=[str(root)], datas=datas,
             hiddenimports=hiddenimports, noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SupplyChainSparks",
          console=False, icon=None)
coll = COLLECT(exe, a.binaries, a.datas, name="SupplyChainSparks")
