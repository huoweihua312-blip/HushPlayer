import os, sys, shutil
root = os.path.abspath("artifacts/qa/r12/data")
shutil.rmtree(root, ignore_errors=True)
os.environ["HUSHPLAYER_DATA_DIR"] = root
os.environ.setdefault("HUSH_CONSOLE", "0")
sys.path.insert(0, ".")
from hushplayer.online import registry as reg_mod
reg = reg_mod.registry(); reg.ensure()
URL = os.environ.get("HUSHPLAYER_PROBE_SUBSCRIPTION", "")
report = reg.install_subscription(url)
print("installed", len(report.installed), "dups", len(report.duplicates), "failed", len(report.failed))
print("summary", report.summary())
for item in report.installed:
    print(" -", item["name"], item["version"], item["filename"])
for name, reason in report.failed[:5]:
    print(" fail", name, reason)
