"""Shared scope and provenance helpers for the isolated Phase 1B analysis."""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # code/, for paths.py
from paths import locate, phase_files, display
from pathlib import Path
import calendar,hashlib,json
import numpy as np
# Files are found with paths.locate(); see code/paths.py.
SPEEDS=np.array([2.5,5,10,15,20,25,30,35,40,45,50,55,60,65,70,75],float)
POLS=["CO2","NOx","PM25"]; POLLUTANT_IDS={90:"CO2",3:"NOx",110:"PM25"}
SOURCES={"SU":(52,53),"CT":(61,62)}
EV={"SU":0.02,"CT":0.005}
WINDOW={"am_peak":[9],"midday":list(range(10,17)),"pm_peak":[17,18]}
FULL={"am_peak":[7,8,9],"midday":list(range(10,17)),"pm_peak":[17,18,19],"night":list(range(1,7))+list(range(20,25))}
CONTEXTS={"window":WINDOW,"full_day":FULL}
ROAD={"Street":5,"Highway":4,"Ramp":4,"Bridge":5,"Tunnel":5,"Unknown":5,"Non-Physical":5,"U-Turn":5}
WEEKDAYS={m:sum(calendar.weekday(2025,m,d)<5 for d in range(1,calendar.monthrange(2025,m)[1]+1)) for m in range(1,11)}
def sha(path):
    with Path(path).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save_json(path,obj):Path(path).write_text(json.dumps(obj,indent=2),encoding="utf-8")

