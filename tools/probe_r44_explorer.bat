@echo off
cd /d F:\Projects\HushPlayer-Reimagined
.venv\Scripts\python.exe -u tools\probe_r44_explorer.py > artifacts\qa\r44\explorer_run.log 2>&1
