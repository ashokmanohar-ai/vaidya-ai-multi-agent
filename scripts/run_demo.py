"""Start synthetic demo. Run from repository root with python scripts/run_demo.py."""
import os,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from dotenv import load_dotenv
load_dotenv(root/'.env', override=False)
os.environ['DEMO_MODE']='true'
os.environ['LLM_PROVIDER']=os.environ.get('LLM_PROVIDER','demo')
from app import app,DB
from vaidya.learning import create_seed_learning
from vaidya.presentation import seed_story
audio_only = os.getenv('AUDIO_ONLY_MODE','').lower() == 'true'
DB.seed_demo(include_patients=not audio_only)
if not audio_only:
    create_seed_learning(DB)
if os.getenv("VAIDYA_EMPTY_DEMO") != "1" and os.getenv("AUDIO_ONLY_MODE", "").lower() != "true":
    count=seed_story(DB,root/"instance")
    if count: print(f"Seeded {count} clearly labeled synthetic report examples for presentation.")
# LangGraph is mandatory for the full multi-agent build; do not silently fall back.
from app import graph_runtime
runtime=graph_runtime()
# Seeded synthetic proposals are given a durable admin approval interrupt at startup.
for suggestion in DB.query("SELECT id FROM learnings WHERE status='suggested' AND supporting_jobs>=5"):
    runtime.prepare_learning_review(suggestion['id'])
port=int(os.getenv('PORT','5055'))
print(f'VAIDYA AI multi-agent evaluation: http://127.0.0.1:{port}')
print(f'Persistent LangGraph checkpoint DB: {runtime.checkpoint_path}')
from vaidya.providers import bedrock_settings
settings=bedrock_settings()
if settings['provider'] == 'bedrock':
    from vaidya.providers import bedrock_auth_configuration
    try:
        auth = bedrock_auth_configuration()
    except RuntimeError as exc:
        raise SystemExit('Bedrock authentication configuration error: ' + str(exc)) from None
    print('Bedrock credential source: ' + auth['mode'] + ' (not yet verified with AWS)')
print(f"Extraction provider: {settings['provider']} | Model: {settings['model']} | AWS Region: {settings['region']}")
from vaidya.audio import asr_status
asr=asr_status()
print(f"Audio ASR: {asr['provider']} / {asr.get('model','unknown')} | Ready: {asr.get('ready',False)}")
print('Parent graph: Orchestrator | Specialist subgraphs: Pathology and Learner')
print('Doctor: doctor@vaidya.demo / DemoDoctor!2026')
print('Administrator: admin@vaidya.demo / DemoAdmin!2026')
print('NOT FOR REAL PATIENT DATA; launch is intentionally local-only.')
app.run(host='127.0.0.1',port=port,debug=False)
