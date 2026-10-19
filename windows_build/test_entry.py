"""Build-only full regression suite; never included in the production EXE."""
import argparse
import json
from pathlib import Path
import unittest
import test_capture_failures
import test_folder_change_review
import test_hashing
import test_partial_states
import test_report_workflow
import test_ui
import test_security
import test_review_modes

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--results',type=Path,required=True)
args=parser.parse_args()
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(module) for module in (
    test_capture_failures,test_folder_change_review,test_hashing,test_partial_states,test_report_workflow,test_ui,test_security,test_review_modes))
result=unittest.TextTestRunner(verbosity=2).run(suite)
receipt={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
         'skipped':len(result.skipped),'frozen_runtime':True}
args.results.parent.mkdir(parents=True,exist_ok=True)
args.results.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
