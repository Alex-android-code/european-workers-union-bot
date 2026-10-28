"""Export only the synthetic end-to-end SQL trace for PostgreSQL replay tests."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ewu.storage import Database
from test_recruitment import RecruitmentTests

statements=[]
original=Database.execute

def captured(self,sql,values=()):
    statements.append([sql,values])
    return original(self,sql,values)

Database.execute=captured
case=RecruitmentTests('test_full_twenty_step_synthetic_scenario')
try:
    case.setUp()
    case.test_full_twenty_step_synthetic_scenario()
finally:
    case.doCleanups()
    Database.execute=original
print(json.dumps(statements))
