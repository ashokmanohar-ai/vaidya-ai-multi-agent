"""Explicit billable Sarvam test for *synthetic*, non-identifiable audio only.

Example (PowerShell):
  python scripts/sarvam_batch_smoke.py --file synthetic_tamil_english.ogg --confirm-synthetic
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / '.env', override=False)

from vaidya.audio import SarvamBatchTranscriber


def main() -> int:
    parser=argparse.ArgumentParser(description='Sarvam V4 batch test with synthetic audio (may incur charges).')
    parser.add_argument('--file',required=True,help='Synthetic, non-identifiable OGG/WAV/MP3/M4A/WebM recording')
    parser.add_argument('--confirm-synthetic',action='store_true',help='Confirm no real patient identifiers/data')
    parser.add_argument('--mode',choices=['codemix','transcribe','verbatim','translit','translate'],default='codemix')
    parser.add_argument('--language-code',choices=['unknown','ta-IN','en-IN'],default='unknown')
    parser.add_argument('--show-transcript',action='store_true',help='Print synthetic transcript to console')
    args=parser.parse_args()
    if not args.confirm_synthetic:
        parser.error('Refusing cloud upload: supply --confirm-synthetic only for de-identified/synthetic audio')
    if os.getenv('ALLOW_REMOTE_SYNTHETIC_INPUT','').lower()!='true':
        parser.error('ALLOW_REMOTE_SYNTHETIC_INPUT=true must be configured explicitly')
    if not os.getenv('SARVAM_API_KEY','').strip():
        parser.error('SARVAM_API_KEY is not configured')
    path=Path(args.file).expanduser().resolve()
    if not path.is_file():
        parser.error('Audio file does not exist')
    engine=SarvamBatchTranscriber(mode=args.mode,language_code=args.language_code)
    print(f'Calling Sarvam with {engine.model} / {engine.mode}; billable remote request. No patient data permitted.')
    result=engine.transcribe([str(path)])
    print('Completed:', result.provider, result.model, '/', result.mode)
    print('Detected language:', ','.join(result.detected_languages))
    print('Job ID:', result.job_ids[0])
    print('Characters:',len(result.text))
    if args.show_transcript:
        print('SYNTHETIC transcript (unverified):\n'+result.text)
    print('Clinical terms, negations and numbers must be checked against the recording.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
