"""Evidence-based learning candidate workflow; never automatically activates skills."""
from collections import Counter
from difflib import SequenceMatcher
from .database import utcnow


def assess_edit(before, after):
    if before.strip()==after.strip():return None
    original=set(before.lower().split())
    new=set(after.lower().split())
    extra=new-original
    if 'signature' in extra or 'signed' in extra or 'signature:' in after.lower():
        return ('signature_block','doctor_added','Doctor repeatedly adds a signature/sign-off block.')
    if 'specimen' in extra:
        return ('specimen_field','doctor_added','Doctor repeatedly adds a specimen detail.')
    return ('general_edited','needs_review','Doctor modified the generated draft; manual pattern review required.')


def record_learning(db,job_id,before,after):
    issue=assess_edit(before,after)
    if not issue:return None
    key,diff_type,description=issue
    # Replayed LangGraph steps may re-enter; never count the same job/pattern twice.
    exists=db.query('SELECT id FROM job_diffs WHERE job_id=? AND pattern_key=?',
                    (job_id,key),one=True)
    if not exists:
        db.execute('INSERT INTO job_diffs(job_id,type,before_text,after_text,pattern_key) VALUES(?,?,?,?,?)',
                   (job_id,diff_type,before[:5000],after[:5000],key))
    evidence=db.query('SELECT COUNT(DISTINCT job_id) AS n FROM job_diffs WHERE pattern_key=?',(key,),one=True)['n']
    if evidence>=5:
        with db.connect() as c:
            c.execute('INSERT INTO learnings(pattern_key,description,supporting_jobs,status,created_at) VALUES(?,?,?,?,?) '
                      'ON CONFLICT(pattern_key) DO UPDATE SET supporting_jobs=excluded.supporting_jobs',
                      (key,description,evidence,'suggested',utcnow()))
    return {'type':diff_type,'pattern':key,'evidence_count':evidence}


def create_seed_learning(db):
    """Synthetic proposed learning for leadership review; no fake reports/clinical evidence."""
    db.execute('INSERT OR IGNORE INTO learnings(pattern_key,description,supporting_jobs,status,created_at) VALUES(?,?,?,?,?)',
               ('demo_signature_example','EXAMPLE ONLY: Add a doctor-signature block after five independent doctor-corrected reports.',
                0,'example_only',utcnow()))
