"""Executable tests for real LangGraph; these must not be skipped in the Windows release gate."""
import pytest
pytest.importorskip('langgraph')
pytest.importorskip('langgraph.checkpoint.sqlite')

from vaidya.database import Database, utcnow
from vaidya.multi_agent import GraphRuntime
from vaidya.learning import create_seed_learning

SAMPLE=('Specimen: appendix. Sections reveal acute inflammation. '
        'Dictated finding: acute appendicitis. Please bold acute appendicitis in the report.')


def runtime(tmp_path,monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER','demo')
    db=Database(tmp_path/'db.sqlite3')
    db.seed_demo()
    create_seed_learning(db)
    return db,GraphRuntime(db,tmp_path/'instance')


def test_graph_subgraphs_compile(tmp_path,monkeypatch):
    db,rt=runtime(tmp_path,monkeypatch)
    try:
        shape=rt.graph.get_graph()
        assert {'authorize_and_route','pathology_agent','learner_agent'}<=set(shape.nodes)
        assert 'extract_structured_fields' in rt.pathology_graph.get_graph().nodes
        assert 'administrator_interrupt' in rt.learner_graph.get_graph().nodes
        assert 'doctor_review_interrupt' in rt.pathology_graph.get_graph().nodes
    finally: rt.close()


def test_pathology_persistence_and_restart(tmp_path,monkeypatch):
    db,rt=runtime(tmp_path,monkeypatch)
    job_id='graph-test-001'
    result=rt.generate(job_id=job_id,doctor_id=1,patient_id=1,hospital_id=1,transcript=SAMPLE)
    assert result['status']=='draft_ready'
    assert (tmp_path/'instance'/'reports'/f'{job_id}.docx').is_file()
    stages=rt.trace(job_id)
    assert any(e['agent']=='pathology_agent' and e['stage']=='extract_structured_fields' for e in stages)
    assert rt.checkpoint_summary(f'vaidya:report:{job_id}')['exists']
    rt.close()
    restarted=GraphRuntime(db,tmp_path/'instance')
    try:
        assert restarted.checkpoint_summary(f'vaidya:report:{job_id}')['pending_nodes']
        # A doctor approval survives a worker restart and is human-resumed.
        with db.connect() as c:
            c.execute('UPDATE jobs SET status=?,final_text=?,approved_by=?,approved_at=? WHERE id=?',
                      ('approved','Doctor reviewed synthetic finding',1,utcnow(),job_id))
        finished=restarted.complete_doctor_review(job_id,1)
        assert finished['status']=='approved'
        assert restarted.checkpoint_summary(f'vaidya:report:{job_id}')['pending_nodes']==[]
        assert db.query('SELECT COUNT(*) n FROM jobs WHERE id=?',(job_id,),one=True)['n']==1
    finally: restarted.close()


def test_orchestrator_blocks_wrong_hospital(tmp_path,monkeypatch):
    db,rt=runtime(tmp_path,monkeypatch)
    try:
        with pytest.raises(PermissionError):
            rt.generate(job_id='bad-hospital',doctor_id=1,patient_id=1,hospital_id=999,transcript=SAMPLE)
        assert not db.query('SELECT id FROM jobs WHERE id=?',('bad-hospital',))
    finally:rt.close()


def test_learning_human_interrupt_resume_and_version(tmp_path,monkeypatch):
    db,rt=runtime(tmp_path,monkeypatch)
    try:
        for i in range(1,6):
            jid=f'learner-{i}'
            rt.generate(job_id=jid,doctor_id=1,patient_id=i,hospital_id=1,transcript=SAMPLE)
            with db.connect() as c:
                job=c.execute('SELECT draft_text FROM jobs WHERE id=?',(jid,)).fetchone()
                c.execute('UPDATE jobs SET status=?,final_text=?,approved_by=?,approved_at=? WHERE id=?',
                         ('approved',job['draft_text']+'\nSignature: Dr. Brindha',1,utcnow(),jid))
            rt.complete_doctor_review(jid,1)
            rt.analyze(jid)
            rt.analyze(jid)  # replay must not increase evidence_count
        suggestion=db.query("SELECT * FROM learnings WHERE pattern_key='signature_block'",one=True)
        assert suggestion['supporting_jobs']==5
        assert db.query("SELECT COUNT(*) n FROM job_diffs WHERE pattern_key='signature_block'",one=True)['n']==5
        rt.prepare_learning_review(suggestion['id'])
        cp=rt.checkpoint_summary(f"vaidya:approval:{suggestion['id']}")
        assert cp['exists'] and cp['pending_nodes']
        rt.close()
        rt=GraphRuntime(db,tmp_path/'instance')
        assert rt.checkpoint_summary(f"vaidya:approval:{suggestion['id']}")['pending_nodes']
        with pytest.raises(PermissionError):
            rt.decide_learning(suggestion['id'],1,'approved')
        assert db.query('SELECT MAX(version) v FROM skills',one=True)['v']==1
        result=rt.decide_learning(suggestion['id'],2,'approved')
        assert result['status']=='decision_recorded'
        assert db.query('SELECT MAX(version) v FROM skills',one=True)['v']==2
        assert db.query('SELECT status FROM learnings WHERE id=?',(suggestion['id'],),one=True)['status']=='approved'
        assert rt.checkpoint_summary(f"vaidya:approval:{suggestion['id']}")['pending_nodes']==[]
    finally:rt.close()


def test_real_bedrock_adapter_graph_integration_with_fake_client(tmp_path, monkeypatch):
    """Runs real LangGraph nodes and checkpointing but FAKE network inference."""
    import json
    from vaidya.providers import BedrockConverseProvider
    import vaidya.multi_agent as module
    db, rt = runtime(tmp_path, monkeypatch)
    monkeypatch.setenv('ALLOW_REMOTE_SYNTHETIC_INPUT', 'true')
    monkeypatch.setenv('LLM_EXTRACTION_MODEL', 'in.openai.gpt-5.6-terra')
    monkeypatch.setenv('BEDROCK_MODELS', 'in.openai.gpt-5.6-terra')

    class FakeClient:
        def converse(self, **request):
            return {'output': {'message': {'content': [{'text': json.dumps({
                'findings': [{'text': 'Appendix inflammation'}],
                'instructions': [{'instruction': 'bold inflammation'}],
                'review_flags': []
            })}]}}, 'usage': {'inputTokens': 100, 'outputTokens': 42}}

    monkeypatch.setattr(module, 'get_provider', lambda: BedrockConverseProvider(client=FakeClient()))
    try:
        result=rt.generate(job_id='bedrock-fake-001',doctor_id=1,patient_id=1,
                           hospital_id=1,transcript=SAMPLE)
        assert result['status']=='draft_ready'
        persisted=db.query('SELECT provider,model,status FROM jobs WHERE id=?',('bedrock-fake-001',),one=True)
        assert persisted['provider']=='aws-bedrock'
        assert persisted['status']=='draft_ready'
        metrics=db.query('SELECT * FROM llm_calls WHERE job_id=?',('bedrock-fake-001',),one=True)
        assert metrics and metrics['input_tokens']==100 and metrics['output_tokens']==42
        assert rt.checkpoint_summary('vaidya:report:bedrock-fake-001')['pending_nodes']
    finally:
        rt.close()
