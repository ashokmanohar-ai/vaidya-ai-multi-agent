"""Synthetic history fixture to present an evidence-backed proposed learning without PHI."""
import json
from pathlib import Path
from .database import utcnow
from .providers import deterministic_extract
from .reports import report_text
from .reports import render_docx, final_docx
from .learning import record_learning

SAMPLE='Specimen: appendix. Sections reveal acute inflammation. Dictated finding: acute appendicitis. Please bold acute appendicitis in the report.'


def seed_story(db,data_dir):
    if db.query("SELECT count(*) AS n FROM jobs WHERE id LIKE 'DEMO-STORY-%'",one=True)['n']:
        return 0
    hospital=db.query('SELECT * FROM hospitals WHERE id=1',one=True)
    # Presentation history always uses synthetic rule-based extraction, even if
    # the user has configured Bedrock for new graph-generated jobs.
    example=deterministic_extract(SAMPLE)
    original={'findings':example.findings,'instructions':example.instructions,
              'review_flags':example.review_flags,'provider':example.provider,
              'model':example.model,
              'draft_text':report_text(example.findings,example.instructions,example.review_flags)}
    for idx in range(1,6):
        patient=db.query('SELECT * FROM patients WHERE id=?',(idx,),one=True)
        job_id=f'DEMO-STORY-{idx:03d}'
        draft=Path(data_dir)/'reports'/f'{job_id}.docx'
        render_docx({'id':job_id},patient,hospital,original['findings'],original['instructions'],original['review_flags'],[],draft)
        db.execute('''INSERT INTO jobs(id,patient_id,doctor_id,hospital_id,report_type,original_transcript,translated_transcript,
            findings_json,instruction_json,draft_text,final_text,draft_filename,image_json,provider,model,status,created_at,approved_at,approved_by)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (job_id,idx,1,1,'histopathology',SAMPLE,SAMPLE,json.dumps(original['findings']),
             json.dumps(original['instructions']),original['draft_text'],original['draft_text']+'\nSignature: Dr. Brindha',
             draft.name,'[]','demo-rules','rules-v1','approved',utcnow(),utcnow(),1))
        final=Path(data_dir)/'reports'/f'{job_id}-doctor-final.docx'
        final_docx(original['draft_text']+'\nSignature: Dr. Brindha',{'id':job_id},patient,hospital,final)
        record_learning(db,job_id,original['draft_text'],original['draft_text']+'\nSignature: Dr. Brindha')
        db.audit(1,'seed_synthetic_approval','job',job_id)
    return 5
