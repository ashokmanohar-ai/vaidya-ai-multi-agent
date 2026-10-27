"""Launch audio-only, non-clinical evaluation interface without sample reports."""
import os
os.environ['AUDIO_ONLY_MODE']='true'
os.environ['VAIDYA_EMPTY_DEMO']='1'
# Demo authentication remains for local testing only; never expose this service on a network.
from pathlib import Path
os.environ.setdefault('VAIDYA_DATA_DIR', str(Path(__file__).resolve().parents[1]/'instance_audio_only'))
from run_demo import *
