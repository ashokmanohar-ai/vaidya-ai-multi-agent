"""Run actual Sarvam batch STT on approved evaluation audio. Billable API call.

No fake transcript, no fallback and no packaged patient data. Writes private
files to a path chosen by the operator; no transcript text printed to console.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env',override=False)
from vaidya.audio import SarvamBatchTranscriber
from scripts.evaluate_transcription import evaluate


def save_private(path: Path, data: str):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8') as stream:
        stream.write(data)
    if os.name=='posix':path.chmod(stat.S_IRUSR|stat.S_IWUSR)


def main():
    parser=argparse.ArgumentParser(description='Real Sarvam transcription (billed; no synthetic fallback)')
    parser.add_argument('--audio',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reference',type=Path,help='independently manually verified verbatim reference')
    parser.add_argument('--confirm-approved-upload',action='store_true')
    args=parser.parse_args()
    if not args.confirm_approved_upload:
        parser.error('Requires --confirm-approved-upload for approved synthetic/de-identified evaluation audio')
    if os.getenv('ALLOW_REMOTE_SYNTHETIC_INPUT','').lower()!='true':
        parser.error('Set ALLOW_REMOTE_SYNTHETIC_INPUT=true only after provider and privacy approval')
    if not args.audio.is_file():
        parser.error('Audio input file is missing')
    response=SarvamBatchTranscriber().transcribe([str(args.audio)])
    if not response.text.strip():
        raise RuntimeError('No transcript from provider; output not generated')
    folder=args.output.resolve()
    save_private(folder/'transcript.txt',response.text)
    provenance={
        'provider':response.provider,'model':response.model,'mode':response.mode,
        'language_codes':response.detected_languages,'job_ids':response.job_ids,
        'audio_sha256':response.audio_sha256,
        'transcript_sha256':hashlib.sha256(response.text.encode('utf-8')).hexdigest(),
        'audio_files_processed':1,
    }
    save_private(folder/'asr_provenance.json',json.dumps(provenance,indent=2,ensure_ascii=False))
    if args.reference:
        result=evaluate(args.reference.read_text(encoding='utf-8'),response.text)
        save_private(folder/'accuracy_metrics.json',json.dumps(result,indent=2,ensure_ascii=False))
        print(f"Reference metrics: WER={result['wer']:.3f}; CER={result['cer']:.3f}; not a clinical validation")
    print('Sarvam completed. Output transcript and provenance saved privately (content not printed).')

if __name__=='__main__':main()
