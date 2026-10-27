"""Reference-based transcription evaluation; no synthesized ground-truth labels.

Requires an independently human-verified verbatim reference transcript in a
file. A formatted pathology report is NOT a valid WER reference. Does not log
patient text; prints aggregate measures and counts only.
"""
from __future__ import annotations
import argparse
import json
import re
import unicodedata
from pathlib import Path


def tokens(text: str) -> list[str]:
    normal = unicodedata.normalize('NFKC', text).casefold()
    normal = re.sub(r'[^\w\u0b80-\u0bff]+', ' ', normal, flags=re.UNICODE)
    return normal.split()


def distance(expected: list[str], actual: list[str]) -> int:
    prior = list(range(len(actual) + 1))
    for i, x in enumerate(expected, start=1):
        current = [i]
        for j, y in enumerate(actual, start=1):
            current.append(min(current[-1] + 1, prior[j] + 1, prior[j - 1] + (x != y)))
        prior = current
    return prior[-1]


def evaluate(reference: str, hypothesis: str, critical_phrases: list[str] | None = None) -> dict:
    rt, ht = tokens(reference), tokens(hypothesis)
    if not rt or not ht:
        raise ValueError('Nonempty human-verified reference and ASR transcript required')
    refc = list(''.join(rt)); hypc = list(''.join(ht))
    missed = []
    for phrase in critical_phrases or []:
        phrase_tokens=tokens(phrase)
        if not phrase_tokens:
            raise ValueError('Critical phrase must be nonempty')
        target=' '.join(phrase_tokens)
        if target not in ' '.join(ht):
            missed.append(phrase)
    return {
        'reference_words':len(rt),'hypothesis_words':len(ht),
        'wer':round(distance(rt,ht)/len(rt),6),
        'cer':round(distance(refc,hypc)/max(1,len(refc)),6),
        'missing_critical_phrase_count':len(missed),
        'missing_critical_phrases':missed,
        'reference_type':'human-verified-verbatim',
        'caution':'WER/CER are screening metrics, never a substitute for clinical source verification',
    }


def main():
    parser=argparse.ArgumentParser(description='Compare actual provider transcript to an independently verified verbatim reference')
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--critical-phrase',action='append',default=[])
    parser.add_argument('--max-wer',type=float,default=0.10)
    parser.add_argument('--max-cer',type=float,default=0.10)
    parser.add_argument('--json-out',type=Path)
    args=parser.parse_args()
    report=evaluate(args.reference.read_text(encoding='utf-8'),args.candidate.read_text(encoding='utf-8'),args.critical_phrase)
    status=(report['wer']<=args.max_wer and report['cer']<=args.max_cer and report['missing_critical_phrase_count']==0)
    report['pass_requested_thresholds']=status
    # Avoid printing any original clinical text (including optional critical phrases).
    print(f"WER={report['wer']:.3f}, CER={report['cer']:.3f}, missing_critical_phrases={report['missing_critical_phrase_count']}, threshold_pass={status}")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True,exist_ok=True)
        args.json_out.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    raise SystemExit(0 if status else 2)

if __name__=='__main__':main()
