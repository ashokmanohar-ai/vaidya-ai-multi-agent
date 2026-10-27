"""Dependency-free persistence and safety tests; not a substitute for real LangGraph tests."""
from vaidya.database import Database, utcnow
from vaidya.learning import record_learning


def test_event_schema_and_idempotent_stage(tmp_path):
    db=Database(tmp_path/'data.sqlite3');db.seed_demo()
    db.execute('INSERT OR IGNORE INTO workflow_events(workflow_id,job_id,agent,stage,status,created_at) VALUES(?,?,?,?,?,?)',
               ('thread-A','job-A','pathology_agent','render','completed',utcnow()))
    db.execute('INSERT OR IGNORE INTO workflow_events(workflow_id,job_id,agent,stage,status,created_at) VALUES(?,?,?,?,?,?)',
               ('thread-A','job-A','pathology_agent','render','completed',utcnow()))
    count=db.query("SELECT COUNT(*) n FROM workflow_events WHERE workflow_id='thread-A'",one=True)['n']
    assert count==1


def test_learning_duplicate_job_cannot_inflate_threshold(tmp_path):
    db=Database(tmp_path/'data.sqlite3');db.seed_demo()
    from vaidya.workflow import run_extraction
    before=run_extraction('Synthetic finding appendix.')['draft_text']
    db.execute('''INSERT INTO jobs(id,patient_id,doctor_id,hospital_id,report_type,
        original_transcript,translated_transcript,findings_json,instruction_json,draft_text,
        draft_filename,image_json,provider,model,status,created_at,final_text,approved_by,approved_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        ('idempotent-job',1,1,1,'histopathology','Synthetic finding appendix.',
         'Synthetic finding appendix.','[]','[]',before,'synthetic.docx','[]',
         'demo-rules','rules-v1','approved',utcnow(),before+'\nSignature: Doctor',1,utcnow()))
    for i in range(10):
        result=record_learning(db,'idempotent-job',before,before+'\nSignature: Doctor')
        assert result['evidence_count']==1
    assert db.query("SELECT COUNT(*) n FROM job_diffs WHERE pattern_key='signature_block'",one=True)['n']==1
    assert db.query("SELECT id FROM learnings WHERE pattern_key='signature_block'")==[]
