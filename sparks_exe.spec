# PyInstaller spec — one-folder build with bundled dashboard + prompts.
import pathlib

from PyInstaller.utils.hooks import collect_data_files

root = pathlib.Path(SPECPATH).resolve()
datas = [
    (str(root / "dashboard" / "dist"), "dashboard/dist"),
    (str(root / "sparks" / "prompts"), "sparks/prompts"),
    (str(root / "settings.yaml"), "."),
    (str(root / "sources.yaml"), "."),
    # trafilatura reads settings.cfg + data/ at import of its config; without
    # these every extraction dies with KeyError: 'min_extracted_size'
    # (justext stoplists are its extraction fallback).
    *collect_data_files("trafilatura"),
    *collect_data_files("justext"),
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
