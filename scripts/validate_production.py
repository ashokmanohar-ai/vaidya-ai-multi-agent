"""Operator preflight of the production engineering candidate (no AWS calls)."""
import subprocess
import sys
import importlib.util

required=('flask','langgraph','langgraph.checkpoint.postgres','sqlalchemy','psycopg','alembic','boto3','docx')
missing=[]
for item in required:
    try:found=importlib.util.find_spec(item)
    except (ImportError,ModuleNotFoundError):found=None
    print(('PASS ' if found else 'MISSING ')+item)
    if not found:missing.append(item)
if missing:
    print('Install requirements-production.txt before validating integration tests.')
    sys.exit(2)
cmd=[sys.executable,'-m','pytest','-q','-rs',
    'production_tests/test_secure_domain.py',
    'production_tests/test_flask_production_api.py',
    'tests/test_flask_e2e.py','tests/test_langgraph_multiagent.py']
print('Running required local framework and domain test suites...')
result=subprocess.run(cmd,check=False)
if result.returncode:
    sys.exit(result.returncode)
print('Local framework suite completed. Next: opt-in disposable PostgreSQL and real AWS integration validation.')
