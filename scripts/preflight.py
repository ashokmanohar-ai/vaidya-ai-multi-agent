"""Read-only environment preflight for the leadership demonstration."""
from importlib.util import find_spec
from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env',override=False)
print('VAIDYA AI · AUDIO-ONLY EVALUATION · PRE-FLIGHT')
print('Python:',sys.version.split()[0])
required=['dotenv','flask','jinja2','docx','PIL','boto3','langgraph','langgraph.checkpoint.sqlite']
missing=[]
for mod in required:
    try: available=find_spec(mod) is not None
    except ModuleNotFoundError: available=False
    print(('PASS' if available else 'MISSING'),mod)
    if not available:missing.append(mod)
print('LangGraph orchestration: REQUIRED')
from vaidya.audio import asr_status
asr=asr_status()
print('Audio ASR provider:', asr['provider'])
print('Audio ASR model:', asr.get('model'))
print('Audio ASR SDK installed:',asr.get('sdk_installed', False))
print('Audio ASR ready:',asr.get('ready',False))
if asr['provider']=='sarvam':
    print('Sarvam key configured:',asr['credentials_configured'])
    print('Remote transcription explicitly permitted:',asr.get('remote_transmission_approved',False))
print('ASR_PROVIDER:',os.getenv('ASR_PROVIDER','faster-whisper'))
print('TRANSLATION_PROVIDER:',os.getenv('TRANSLATION_PROVIDER','passthrough'))
print('ASR installation and real credentials REQUIRED for the audio-only workflow.')
print('Demo mode will be enabled by scripts/run_demo.py')
from vaidya.providers import bedrock_settings
settings=bedrock_settings()
print('LLM provider:',settings['provider'])
print('Bedrock model:',settings['model'])
print('Bedrock region:',settings['region'])
print('Remote synthetic opt-in:',settings['remote_opt_in'])
print('Bedrock bearer token present:',settings['credential_configured'])
print('AWS profile configured:',settings['aws_profile_configured'])
print('AWS static credential override present:',settings['aws_static_keys_configured'])
print('Bedrock authentication mode:',settings['auth_mode'])
from vaidya.providers import bedrock_auth_configuration
try:
    auth = bedrock_auth_configuration()
    print('Bedrock credential-source selection: PASS (' + auth['mode'] + ')')
except RuntimeError as error:
    print('Bedrock credential-source selection: FAIL - ' + str(error))
    if settings['provider']=='bedrock':
        missing.append('Bedrock credential-source configuration')
print('Local instance disk exists:',(ROOT/'instance').exists())
if os.getenv('AUDIO_ONLY_MODE','').lower() == 'true' and not asr.get('ready'):
    missing.append('configured live ASR (SARVAM_API_KEY/SDK/remote authorization)')
if missing:
    print('NOT READY — install requirements-dev.txt and configure authorized Sarvam access:', ', '.join(missing))
    sys.exit(1)
print('DEPENDENCY CHECK PASSED. Next: python scripts/run_real_audio.py')
