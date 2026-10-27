"""Conservative source-to-extraction warning checks; not clinical validation.

All report claims still require doctor review. This module prioritizes numeric,
laterality and negation discrepancies and never certifies diagnostic accuracy.
"""
from __future__ import annotations
import re

NUMBER=re.compile(r'(?<!\w)[+-]?(?:\d+(?:[.,]\d+)?)(?!\w)')
LATERALITY={'left','right','bilateral','unilateral'}
NEGATIONS={'no','not','negative','without','absent','denies'}


def numeric_tokens(text:str)->set[str]:
    return {x.replace(',','') for x in NUMBER.findall(text or '')}


def clinical_fidelity_warnings(source:str,findings:list[dict],translated:str|None=None)->list[str]:
    """Flag likely source mismatches. Not an entailment oracle."""
    reported=' '.join(str(item.get('text','')) for item in findings)
    source_lower=source.lower()
    output_lower=reported.lower()
    flags=[]
    source_numbers=numeric_tokens(source)
    extra=numeric_tokens(reported)-source_numbers
    if extra:
        flags.append('Possible unsupported numbers in extracted findings: '+', '.join(sorted(extra))[:110]+'. Verify against dictation.')
    for term in sorted(LATERALITY):
        if re.search(r'\b'+term+r'\b',output_lower) and not re.search(r'\b'+term+r'\b',source_lower):
            flags.append('Laterality term '+term+' not found in original dictation; verify.')
    # A heuristic only: translated language can legitimately change negation words.
    if translated and translated!=source:
        source_nums=numeric_tokens(source)
        missing=source_nums-numeric_tokens(translated)
        if missing:
            flags.append('Translation may have dropped original numeric values: '+', '.join(sorted(missing))[:110]+'.')
    if not reported.strip():flags.append('No dictated findings extracted. Doctor clarification required.')
    return flags
