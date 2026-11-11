"""Read-only NVivo runtime preflight."""
import os, platform, json, shutil
from pathlib import Path

def check():
    install = Path(os.environ.get("NVIVO_INSTALL_DIR", "C:/Program Files/Lumivero/NVivo 15"))
    exe = os.environ.get("NVIVO_LOCALDB_EXE", "C:/Program Files/Microsoft SQL Server/150/Tools/Binn/SqlLocalDB.exe")
    checks = {"windows": platform.system() == "Windows", "nvivo": (install / "NVivo.exe").is_file(), "converter": (install / "Converters/QDPX/QSR.Tools.QDPXExporter.exe").is_file(), "localdb": Path(exe).is_file(), "powershell": shutil.which("powershell.exe") is not None}
    return {"ready": all(checks.values()), "checks": checks, "install": str(install), "tested_runtime": "NVivo 15.6.1.3; other versions require live verification"}
if __name__ == "__main__":
    report = check()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ready"] else 1)
