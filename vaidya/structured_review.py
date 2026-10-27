"""Human-controlled, synthetic-data-only structured histopathology review.

ASR text is evidence to inspect, not medical truth. Candidate strings are always
UNVERIFIED; a reviewer must confirm each field using the source recording.
"""
from __future__ import annotations
from datetime import datetime
import re
from typing import Mapping

FIELDS = (
    ('specimen', 'Specimen', 200),
    ('referring_doctors', 'Referring doctor(s)', 260),
    ('biopsy_id', 'Biopsy / accession number', 60),
    ('received_date', 'Received date (DD/MM/YYYY)', 10),
    ('reported_date', 'Reported date (DD/MM/YYYY)', 10),
    ('gross', 'Gross description', 2400),
    ('microscopy', 'Microscopy', 4000),
    ('impression', 'Impression', 1200),
)

UNRESOLVED = re.compile(r'(?i)\b(?:unverified|not validated|not clearly dictated|patient record must match|stop.+conflicting|asr is unverified)\b|\[[^\]]*(?:unknown|missing|verify|dictated)[^\]]*\]')
UNSAFE_ATYPICAL = re.compile(r'\b(?:and|or|with|are|of)\s+atypical\s+cells\b', re.I)


def candidates(assessment: Mapping) -> list[dict]:
    """Literal ASR candidates, with no fabricated missing dates or clinical negations."""
    sections=assessment.get('sections_unverified') or {}
    context=sections.get('context') or ''
    original=' '.join([context,sections.get('gross') or '',sections.get('microscopy') or ''])
    specimen_match=re.search(r'\bspecimen\s*[:\-]?\s*(?:is\s+)?([\w-]+)',context,re.I)
    doctors=[]
    for fragment in re.findall(r'\b(?:dr\.?|doctor)\s+[\w]+(?:\s+[\w]+){0,2}',
                                context+' '+' '.join(assessment.get('instruction_candidates') or []),re.I):
        fragment=re.sub(r'\s+(?=specimen|biopsy|number|slash|report|reported|gross|age|female|male|and\b|with\b)', '',fragment,flags=re.I)
        if fragment.lower() not in [d.lower() for d in doctors]: doctors.append(fragment)
    dates=assessment.get('dates_as_spoken') or {}
    date_received=dates.get('received','')
    date_reported=dates.get('reported','')
    found={
        'specimen':specimen_match.group(1) if specimen_match else '',
        'referring_doctors':' / '.join(doctors) if doctors else '',
        'biopsy_id':assessment.get('biopsy_id_as_spoken') or '',
        'received_date':date_received if re.fullmatch(r'\d{2}/\d{2}/\d{4}',date_received) else '',
        'reported_date':date_reported if re.fullmatch(r'\d{2}/\d{2}/\d{4}',date_reported) else '',
        'gross':sections.get('gross') or '',
        'microscopy':sections.get('microscopy') or '',
        'impression':sections.get('impression') or '',
    }
    return [{'key':key,'label':label,'limit':length,'candidate':found[key],
             'source_status':'ASR CANDIDATE — NOT VERIFIED' if found[key] else 'MISSING / NEEDS MANUAL ENTRY'}
             for key,label,length in FIELDS]


def validate_fields(form: Mapping, *, assessment: Mapping, patient: Mapping) -> tuple[dict,list[str]]:
    """Fail closed; caller must verify every required field individually."""
    errors=list(assessment.get('blocking_issues') or [])
    if form.get('attest') != 'yes':errors.append('Doctor review attestation is required')
    if assessment.get('has_audio'):
        for check in ('verified_audio','verified_identity','verified_numbers','verified_negations','verified_instructions'):
            if form.get(check)!='yes':errors.append('Required verification is missing: '+check)
    structured={}
    for key, label, limit in FIELDS:
        value=str(form.get(key) or '').strip()
        structured[key]=value
        if not value: errors.append(f'{label}: required; enter a verified value')
        if len(value)>limit:errors.append(f'{label}: longer than {limit} characters')
        if '\x00' in value or '\r' in value: errors.append(f'{label}: unsupported character')
        if UNRESOLVED.search(value):errors.append(f'{label}: unverified placeholder or draft warning remains')
        if form.get('confirmed_'+key)!='yes':errors.append(f'{label}: independent source verification required')
    for field in ('received_date','reported_date'):
        value=structured[field]
        if value:
            try:
                parsed=datetime.strptime(value,'%d/%m/%Y')
                if parsed.strftime('%d/%m/%Y') != value: raise ValueError('strict date required')
            except ValueError:errors.append(f'{field}: must be a real date in DD/MM/YYYY format')
    if structured['received_date'] and structured['reported_date']:
        try:
            if datetime.strptime(structured['reported_date'],'%d/%m/%Y') < datetime.strptime(structured['received_date'],'%d/%m/%Y'):
                errors.append('Reported date cannot precede received date')
        except ValueError:pass
    accession=structured['biopsy_id']
    if accession and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9./-]{2,59}',accession):
        errors.append('Biopsy/accession ID must be an explicit verified identifier, without spaces')
    if UNSAFE_ATYPICAL.search(structured['microscopy']):
        errors.append('Microscopy contains ambiguous positive atypical-cell phrasing; resolve against audio')
    if assessment.get('has_audio') and not str(patient.get('name') or '').strip():
        errors.append('Selected patient is missing a name')
    return structured, list(dict.fromkeys(errors))


def formatted_report(patient:Mapping, fields:Mapping)->str:
    """Deterministic text for downstream audit/diff. No inference or auto-correction."""
    content=[
        'HISTOPATHOLOGY REPORT — AUDIO-DERIVED CLINICIAN REVIEWED' if str(patient.get('code','')).startswith('AUDIO-') else 'HISTOPATHOLOGY REPORT — SYNTHETIC CLINICIAN REVIEWED',
        f"Patient: {patient.get('name','')}  Reference: {patient.get('code','')}",
        f"Age / Sex: {patient.get('age','')} / {patient.get('sex','')}",
    ]
    for key,label,_ in FIELDS:
        content.append(f'{label}: {fields[key]}')
    return '\n'.join(content)


def reconcile_minor_name_spelling(assessment: Mapping, patient: Mapping, form: Mapping) -> tuple[dict,str]:
    """Allow explicit, audited ASR spelling corrections, never unrelated identities.

    Date/age/sex conflicts and distant names remain blockers. The *linked*
    synthetic record is not edited; raw ASR stays unchanged.
    """
    clone=dict(assessment)
    blockers=list(clone.get('blocking_issues') or [])
    if not blockers:return clone,''
    if len(blockers)!=1 or not blockers[0].startswith('PATIENT IDENTITY CONFLICT:'):
        return clone,''
    if form.get('resolve_name_spelling')!='yes' or form.get('verified_audio')!='yes':
        return clone,''
    note=str(form.get('name_resolution_note') or '').strip()
    if len(note)<18 or len(note)>500:return clone,''
    spoken=str((clone.get('spoken_patient') or {}).get('name') or '').lower().strip()
    linked=str(patient.get('name') or '').lower().strip()
    spoken=re.sub(r'[^a-z]','',spoken);linked=re.sub(r'[^a-z]','',linked)
    # Short/common names are not safe for approximate matching.
    if min(len(spoken),len(linked))<5 or abs(len(spoken)-len(linked))>2:return clone,''
    prior=list(range(len(linked)+1))
    for i,a in enumerate(spoken,1):
        cur=[i]
        for j,b in enumerate(linked,1):
            cur.append(min(cur[-1]+1,prior[j]+1,prior[j-1]+int(a!=b)))
        prior=cur
    if prior[-1]>1:return clone,''
    clone['blocking_issues']=[]
    clone['manual_name_reconciliation_required']=True
    return clone,note


def verified_audio_patient(form: Mapping, *, candidate: Mapping) -> tuple[dict, list[str], str]:
    """Require explicit reviewer confirmation for an AUDIO-* identity candidate.

    The raw ASR and its candidate stay immutable in the job. Differences require
    an evidence note; they are never inferred, autocompleted or fabricated.
    """
    errors=[]
    name=str(form.get('patient_name') or '').strip()
    age_raw=str(form.get('patient_age') or '').strip()
    sex=str(form.get('patient_sex') or '').strip()
    note=str(form.get('identity_correction_note') or '').strip()
    if not re.fullmatch(r"[^\W\d_][\w .'-]{1,79}",name,re.UNICODE):
        errors.append('Patient name must be verified against source recording')
    if not age_raw.isascii() or not age_raw.isdigit() or int(age_raw or '-1')>120:
        errors.append('Patient age must be verified (0–120)')
    if sex not in ('Female','Male','Other'):
        errors.append('Patient sex must be verified')
    if form.get('confirmed_patient_identity') != 'yes':
        errors.append('Patient identity requires explicit source verification')
    result={'name':name,'age':int(age_raw) if age_raw.isascii() and age_raw.isdigit() else None,
            'sex':sex,'code':candidate.get('code','')}
    changed=any(str(result.get(k) or '').casefold()!=str(candidate.get(k) or '').casefold()
                for k in ('name','age','sex'))
    if changed and not (18<=len(note)<=500):
        errors.append('Explain any missing or corrected patient details using source audio evidence (18–500 characters)')
    return result, errors, note if changed else ''
