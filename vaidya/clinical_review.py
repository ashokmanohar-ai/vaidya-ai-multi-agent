"""Conservative documentation-level checks for SYNTHETIC pathology dictation.

This module does NOT infer clinical truth or correct speech recognition. It creates
candidate section boundaries and identifies issues that require a human to listen
to the source and reconcile patient metadata. Neither normalisation nor doctor
attestation can turn unchecked model text into verified clinical findings.
"""
from __future__ import annotations

import re
from typing import Any

WORD = r"[\w.'-]+"
SECTION_RE = re.compile(
    r"\b(?P<section>gross(?:\s+(?:description|examination|examined))?|"
    r"microscopy|microscopic(?:\s+(?:description|examination))?|"
    r"impression|diagnosis)\s*[:\-]?\s*", re.I
)
NAME_RE = re.compile(
    r"\b(?:patient\s+name\s*[:\-]?\s*)?(?:mrs|mr|ms|miss)\.?\s+"
    r"(?P<name>[\w]+(?:[ -][\w]+){0,3}?)(?=\s+(?:age\b|aged\b|\d{1,3}\s*(?:years?|yrs?)|"
    r"female\b|male\b|referred\b|specimen\b|biopsy\b|gross\b|$)|[,.])", re.I
)
AGE_RE = re.compile(r"\b(?:age\s*[:\-]?\s*|aged\s+)(\d{1,3})\b|\b(\d{1,3})\s*(?:years?\s*old|y/?o)\b", re.I)
SEX_RE = re.compile(r"\b(?:sex\s*[:\-]?\s*)?(female|male)\b", re.I)
DATE_RE = re.compile(r"\b(received|reserved|reported)\s*(?:on|date|:|-)?\s*(\d{1,2}(?:[/-]\d{1,2}(?:[/-]\d{2,4})?)?|\d{4}-\d{2}-\d{2})\b", re.I)
NEGATED_ATYPICAL_RE = re.compile(r"\b(?:no|without|negative\s+for|absence\s+of|not\s+seen|not)\s+(?:(?:\w+\s+){0,3})atypical\s+cells\b", re.I)
ATYPICAL_RE = re.compile(r"\batypical\s+cells\b", re.I)
UNSAFE_POSITIVE_RE = re.compile(r"\b(?:and|or|are|of|with)\s+atypical\s+cells\b", re.I)
REFERRAL_EDIT_RE = re.compile(
    r"(?:\b(?:add|include|insert|change|update|put|slash)\b[^.!?]{0,150}\b(?:dr|doctor)\b|"
    r"\b(?:referred\s+by|refer\s+by)\s+(?:dr\.?|doctor)\b[^!?]{0,90}/\s*(?:dr\.?|doctor)\b)", re.I
)


def _normal_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^(?:mrs|mr|ms|miss)\.?\s+", "", value.strip(), flags=re.I).lower())


def _uniq(seq: list[str]) -> list[str]:
    return list(dict.fromkeys(x for x in seq if x))


def _section_name(label: str) -> str:
    low = label.lower()
    if low.startswith('gross'): return 'gross'
    if low.startswith('micro'): return 'microscopy'
    return 'impression'


def _split_sections(text: str) -> dict[str, str]:
    """Segment only at explicit dictated headings, never fabricate content."""
    text = (text or '').strip()
    sections = {'context': '', 'gross': '', 'microscopy': '', 'impression': ''}
    hits = list(SECTION_RE.finditer(text))
    if not hits:
        sections['context'] = text[:16000]
        return sections
    sections['context'] = text[:hits[0].start()].strip(' .;:\n')
    for i, hit in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        snippet = text[hit.end():end].strip(' .;:\n')
        section = _section_name(hit.group('section'))
        if section == 'impression':
            # End-of-dictation document edit commands do not belong in diagnosis.
            match = re.search(r"\b(?:it\s+is\s+)?referred\s+by\s+(?:dr|doctor)\b", snippet, re.I)
            if match and match.start() > 0:
                snippet = snippet[:match.start()].strip(' .;:\n')
        sections[section] = (sections[section] + '\n' + snippet).strip() if sections[section] else snippet
    return sections


def dictated_patient(original: str) -> dict[str, Any]:
    """Capture only literal patient demographics found in ASR. Missing is empty/None."""
    original = str(original or '').strip()
    names = list(NAME_RE.finditer(original))
    # Some Indian-English recordings dictate 'patient name Ananya' without Mrs/Ms.
    # Require an explicit patient-name label, not a free-floating capitalised word.
    labelled = re.search(
        r'\bpatient\s+name\s*[:\-]?\s*(?:is\s+)?(?:(?:mrs|mr|ms|miss)\.?\s*)?'
        r'(?P<name>[\w]+(?:[ -][\w]+){0,2}?)'
        r'(?=\s+(?:age\b|aged\b|\d{1,3}\s*(?:years?|yrs?)|female\b|male\b|'
        r'referred\b|specimen\b|biopsy\b|gross\b|$)|[,.])', original, re.I)
    age_match = AGE_RE.search(original)
    sex_match = SEX_RE.search(original)
    return {
        'name': names[0].group('name').strip() if names else (labelled.group('name').strip() if labelled else ''),
        'age': int(next(x for x in age_match.groups() if x is not None)) if age_match else None,
        'sex': sex_match.group(1).title() if sex_match else '',
    }


def assess_report(patient: dict[str, Any], original: str, extracted_findings: list[dict],
                  instructions: list[dict], *, audio_present: bool = False) -> dict[str, Any]:
    """Assess a report against *linked* patient identity and the original ASR text.

    Returns candidates, warnings and hard blockers. No fact is populated from a
    separate reference document; the source transcript remains authoritative as
    the current *unverified* record of what ASR captured.
    """
    original = str(original or '').strip()
    text = ' '.join(str(x.get('text', '')) for x in extracted_findings)
    spoken = dictated_patient(original)
    spoken_name, spoken_age, spoken_sex = spoken['name'], spoken['age'], spoken['sex']
    blocking: list[str] = []
    warnings: list[str] = []
    labels = {'name': spoken_name, 'age': spoken_age, 'sex': spoken_sex}
    linked = {'name': str(patient.get('name') or ''), 'age': patient.get('age'),
              'sex': str(patient.get('sex') or ''), 'code': str(patient.get('code') or '')}
    if spoken_name and _normal_name(spoken_name) != _normal_name(linked['name']):
        blocking.append(f"PATIENT IDENTITY CONFLICT: speech says '{spoken_name}' but selected record is '{linked['name']}'. Select a matching synthetic patient before generating a new draft; never silently change the report header.")
    if spoken_age is not None and patient.get('age') is not None and spoken_age != int(patient['age']):
        blocking.append(f"PATIENT AGE CONFLICT: speech says {spoken_age} but selected record says {patient['age']}.")
    if spoken_sex and linked['sex'] and spoken_sex.lower() != linked['sex'].lower():
        blocking.append(f"PATIENT SEX CONFLICT: speech says {spoken_sex} but selected record says {linked['sex']}.")
    dates = {}
    for m in DATE_RE.finditer(original):
        kind, value = m.group(1).lower(), m.group(2)
        if kind == 'reserved': kind = 'received'  # suspect ASR rendering; never silently fix its numeric value
        dates[kind] = value
        if not re.fullmatch(r'(?:\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4}-\d{2}-\d{2})', value):
            warnings.append(f"DATE NOT VERIFIED: '{kind} {value}' lacks a reliable date format; check the recording and enter a verified date manually.")
    biopsy_match = re.search(r'\b(?:biopsy|accession|specimen)\s*(?:number|no\.?|id)\s*[:#-]?\s*([\w/-]{1,32})', original, re.I)
    biopsy_id = biopsy_match.group(1) if biopsy_match else ''
    if biopsy_id and re.fullmatch(r'\d{1,5}', biopsy_id):
        warnings.append('BIOPSY ID NEEDS VERIFICATION: number-only dictation may omit prefix, year or separators; never construct an identifier from assumptions.')
    if ATYPICAL_RE.search(original + ' ' + text):
        neg_src = bool(NEGATED_ATYPICAL_RE.search(original))
        neg_out = bool(NEGATED_ATYPICAL_RE.search(text))
        if neg_src != neg_out:
            blocking.append('CRITICAL NEGATION CONFLICT: source transcription and extracted findings disagree about negation of atypical cells.')
        elif audio_present and not neg_src:
            warnings.append('HIGH RISK ASR: atypical cells mentioned without a clear negation. Listen to the original recording; verify whether the speaker said NO atypical cells.')
        if UNSAFE_POSITIVE_RE.search(text) and not neg_out:
            warnings.append("AMBIGUOUS CELL FINDING: 'and/or atypical cells' is not equivalent to 'no atypical cells'. Doctor must resolve by listening to the recording.")
    if audio_present and str(patient.get('code','')).startswith('AUDIO-'):
        for field, value in labels.items():
            if value in ('', None):
                warnings.append(f'PATIENT {field.upper()} NOT CAPTURED: fill in only after listening to source audio.')
        warnings.append('Patient details below are transcription candidates, not verified registration identity.')
    if audio_present:
        warnings.append('ASR IS UNVERIFIED: check names, dates, measurements, pathology terms and negation against the source audio before sign-off.')
    candidates = _split_sections(original)
    candidate_instructions = [str(i.get('instruction', '')).strip() for i in instructions]
    tail = re.search(r"\b(?:it\s+is\s+)?referred\s+by\s+(?:dr|doctor)\b.{0,150}$", original, re.I)
    if tail and REFERRAL_EDIT_RE.search(tail.group()):
        candidate_instructions.append('Referral edit candidate (verify against source): ' + tail.group().strip())
        warnings.append('REFERRAL EDIT: a possible late dictation instruction was detected. Verify both referring doctors; do not insert as a pathological observation.')
    if not any(candidates[k] for k in ('gross', 'microscopy', 'impression')):
        warnings.append('No explicit report section headings detected. Do not infer a structured diagnosis from unlabelled dictation.')
    return {
        'spoken_patient': labels, 'linked_patient': linked, 'dates_as_spoken': dates,
        'biopsy_id_as_spoken': biopsy_id, 'sections_unverified': candidates,
        'instruction_candidates': _uniq(candidate_instructions),
        'blocking_issues': _uniq(blocking), 'review_warnings': _uniq(warnings),
        'has_audio': bool(audio_present), 'clinical_ready': False,
    }


def final_document_issues(final_text: str, assessment: dict) -> list[str]:
    """Block obviously unresolved ASR errors. This remains no substitute for review."""
    issues = list(assessment.get('blocking_issues') or [])
    text = final_text or ''
    # These are artefacts of the AI draft template and must not be passed off
    # as clinician-finalized content. Source dictation may be quoted by a
    # clinician, but the final report cannot contain unresolved placeholders.
    unresolved = (
        r'\bDRAFT\s*[/—–-]\s*NOT VALIDATED\b',
        r'\bPATIENT RECORD MUST MATCH SOURCE DICTATION\b',
        r'\b(?:GROSS DESCRIPTION|MICROSCOPY|IMPRESSION)\s*[—–-]\s*UNVERIFIED\b',
        r'\[Not clearly dictated[^]]*\]',
        r'\bSTOP\s*[—–-]\s*conflicting source details\b',
    )
    if any(re.search(pattern, text, flags=re.I) for pattern in unresolved):
        issues.append('Final text still contains AI draft warnings, missing-section placeholders or unresolved conflicts; prepare a corrected final document.')
    if assessment.get('has_audio'):
        # Fail closed on *any* ambiguous/positive atypical-cell clause.
        # A separate negated mention elsewhere must not cancel it out.
        if UNSAFE_POSITIVE_RE.search(text):
            issues.append('Final text still contains ambiguous atypical-cell wording; reconcile every occurrence against audio before approval.')
        for kind, value in (assessment.get('dates_as_spoken') or {}).items():
            if value and not re.search(r'[/\-]', value):
                if re.search(r'\b' + re.escape(kind) + r'\s*(?:on|date|:|-)?\s*' + re.escape(value) + r'\b', text, re.I):
                    issues.append(f"Final text still contains malformed '{kind} {value}'. Verify/correct or omit it.")
    return _uniq(issues)
