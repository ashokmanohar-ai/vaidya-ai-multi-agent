"""Strict release validation. DO NOT skip Flask/LangGraph tests for a live presentation."""
from __future__ import annotations
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REQUIRED=['dotenv','flask','langgraph','langgraph.checkpoint.sqlite','docx','PIL','boto3']
errors=[]
for module in REQUIRED:
    try: ok=importlib.util.find_spec(module) is not None
    except ModuleNotFoundError: ok=False
    print(('PASS' if ok else 'MISSING'),module)
    if not ok: errors.append(module)
if errors:
    print('VALIDATION BLOCKED: Install dependencies: python -m pip install -r requirements-dev.txt')
    raise SystemExit(2)
cmd=[sys.executable,'-m','pytest','-v','-ra',
     'tests/test_domain.py','tests/test_bedrock_adapter.py','tests/test_workflow_contracts.py','tests/test_langgraph_multiagent.py','tests/test_flask_e2e.py',
     'tests/test_multilingual_pipeline.py','tests/test_sarvam_batch.py','tests/test_clinical_fidelity.py',
     'tests/test_skill_application.py','tests/test_graph_initialization_regression.py',
     'tests/test_clinical_review_gate.py', 'tests/test_structured_review.py',
     'tests/test_real_audio_pipeline.py']
print('Running required real module tests:', ' '.join(cmd), flush=True)
r=subprocess.run(cmd,cwd=ROOT,check=False,capture_output=True,text=True)
print(r.stdout)
if r.stderr:print(r.stderr,file=sys.stderr)
import re
if r.returncode:raise SystemExit(r.returncode)
if re.search(r'\b[1-9]\d* skipped\b',r.stdout):
    print('VALIDATION FAILED: Required Flask or LangGraph tests were skipped')
    raise SystemExit(3)
print('PASSED: domain, safety review gates, persisted LangGraph, Flask web/API tests')
