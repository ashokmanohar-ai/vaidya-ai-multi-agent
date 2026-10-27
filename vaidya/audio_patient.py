"""Persist an unverified patient candidate directly from the actual ASR transcript.

No demo patients, expected reference documents or hard-coded demographics are used.
Patient fields absent from ASR remain absent; clinicians verify them at review.
"""
from __future__ import annotations
from .clinical_review import dictated_patient


def attach_patient_candidate(db, *, job_id: str, hospital_id: int,
                             transcript: str, audio_hashes: list[str]) -> int:
    """Create/reuse a per-job candidate only for successful audio transcription.

    This technical patient key is not an accession number or patient identifier.
    """
    if not transcript or not transcript.strip() or not audio_hashes or not all(audio_hashes):
        raise ValueError('A nonempty audio-derived ASR response and provenance are required')
    if not job_id or not isinstance(hospital_id, int):
        raise ValueError('Job and hospital are required')
    spoken = dictated_patient(transcript)
    code = 'AUDIO-' + job_id
    with db.connect() as conn:
        linked = conn.execute('SELECT id,name,age,sex,hospital_id FROM patients WHERE code=?', (code,)).fetchone()
        if linked:
            if linked['hospital_id'] != hospital_id:
                raise PermissionError('Audio candidate cross-hospital mismatch')
            if (linked['name'], linked['age'], linked['sex'] or '') != (
                spoken['name'], spoken['age'], spoken['sex']):
                raise RuntimeError('Audio candidate replay differs from stored source identity')
            return linked['id']
        record = conn.execute(
            'INSERT INTO patients(code,name,age,sex,hospital_id) VALUES(?,?,?,?,?)',
            (code, spoken['name'], spoken['age'], spoken['sex'] or None, hospital_id))
        return record.lastrowid
