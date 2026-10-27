"""Executable SQLAlchemy unit tests. No Flask, Bedrock, network, or PHI required."""
import os
from pathlib import Path
from datetime import timedelta
import pytest
from sqlalchemy import select,update
from production.passwords import create_hash,verify_hash
from production.repository import Repository,now
from production.tables import jobs,work,learnings,users
from production.settings import Settings
from production.storage import PrivateS3
from production.documents import render_draft,render_final,extract_text

@pytest.fixture
def context(tmp_path):
    repo=Repository('sqlite:///'+str(tmp_path/'test.db'))
    repo.migrate_for_test()
    boot=repo.bootstrap('Synthetic Test Hospital','admin@sample.invalid','Test Administrator','long-secret-first-login')
    doc=repo.add_user(boot['administrator_id'],boot['hospital_id'],'Dr Test','doctor@sample.invalid','another-valid-long-password','doctor')
    patient=repo.add_patient(doc,boot['hospital_id'],'TEST-100','Only Synthetic')
    return repo,boot,doc,patient

def test_password_hash_secure():
    v=create_hash('a quite strong passphrase')
    assert 'strong passphrase' not in v
    assert verify_hash('a quite strong passphrase',v)
    assert not verify_hash('wrong',v)
    assert not verify_hash('anything','invalid-hash')
    with pytest.raises(ValueError):create_hash('short')

def test_bootstrap_rejects_second_admin(context):
    r,*_=context
    with pytest.raises(RuntimeError):r.bootstrap('x','b@example.test','new','not-this-time-password')

def test_login_and_lockout(context):
    r,b,doc,p=context
    assert r.authenticate('doctor@sample.invalid','another-valid-long-password')['id']==doc
    for _ in range(5):assert r.authenticate('doctor@sample.invalid','wrong') is None
    assert r.authenticate('doctor@sample.invalid','another-valid-long-password') is None
    with r.engine.begin() as c:c.execute(update(users).where(users.c.id==doc).values(locked_until=now()-timedelta(minutes=1)))
    assert r.authenticate('doctor@sample.invalid','another-valid-long-password')['id']==doc

def test_role_and_tenant_isolation(context):
    r,b,doc,p=context
    with pytest.raises(PermissionError):r.authorize_actor(b['administrator_id'],b['hospital_id'],'doctor')
    with pytest.raises(PermissionError):r.authorized_patient(doc,'fake-hospital',p)
    with pytest.raises(PermissionError):r.get_job('other-user','job')

def test_idempotent_job_create(context):
    r,b,doc,p=context
    key='hospital/'+b['hospital_id']+'/jobs/'+'11111111-1111-1111-1111-111111111111'+'/input.txt'
    jid,created=r.create_job(doc,b['hospital_id'],p,key,'unique-test-idempotency')
    j2,created2=r.create_job(doc,b['hospital_id'],p,key,'unique-test-idempotency')
    assert jid==j2 and created and not created2
    assert r.get_job(doc,jid)['status']=='queued'

def test_queue_atomic_claim_and_success(context):
    r,b,doc,p=context
    jid,_=r.create_job(doc,b['hospital_id'],p,'private-key','unique-test-idempotency')
    first=r.claim('worker-1')
    assert first['job_id']==jid and first['attempts']==1
    assert r.claim('worker-2') is None
    r.completed(first['id'])
    assert r.claim('worker-3') is None

def test_retry_backoff_and_exhaustion(context):
    r,b,doc,p=context
    jid,_=r.create_job(doc,b['hospital_id'],p,'private-key','unique-test-idempotency')
    task=r.claim('worker-1')
    r.failed(task['id'],'NetworkUnavailable',max_attempts=1)
    with r.engine.connect() as c:
        status=c.execute(select(work.c.status).where(work.c.id==task['id'])).scalar()
        js=c.execute(select(jobs.c.status).where(jobs.c.id==jid)).scalar()
    assert status=='failed' and js=='failed'

def test_approval_requires_draft(context):
    r,b,doc,p=context
    jid,_=r.create_job(doc,b['hospital_id'],p,'private-key','unique-test-idempotency')
    with pytest.raises(ValueError):r.approve(doc,jid,'signed-key')
    r.set_draft(jid,'draft-key','test-model')
    r.approve(doc,jid,'final-key')
    with pytest.raises(ValueError):r.approve(doc,jid,'second-final')
    with r.engine.connect() as c:
        tasks=c.execute(select(work.c.kind).where(work.c.job_id==jid)).scalars().all()
    assert set(tasks)=={'generate','resume'}

def test_learning_decision_requires_evidence(context):
    r,b,doc,p=context
    from production.tables import learnings
    from production.repository import ident
    lid=ident()
    with r.engine.begin() as c:c.execute(learnings.insert().values(id=lid,hospital_id=b['hospital_id'],specialty='pathology',
             pattern='signature_block',support=4,description='Template only',status='suggested'))
    with pytest.raises(ValueError):r.approve_learning(b['administrator_id'],lid,'approved')
    with r.engine.begin() as c:c.execute(update(learnings).where(learnings.c.id==lid).values(support=5))
    r.approve_learning(b['administrator_id'],lid,'approved')
    with pytest.raises(ValueError):r.approve_learning(b['administrator_id'],lid,'approved')

def test_settings_fail_closed(monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setenv('DATABASE_URL','sqlite:///fake.db')
    monkeypatch.setenv('FLASK_SECRET_KEY','x'*64)
    with pytest.raises(RuntimeError,match='PostgreSQL'):Settings.load()
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://example/db')
    monkeypatch.setenv('VAIDYA_S3_BUCKET','b')
    monkeypatch.setenv('VAIDYA_S3_KMS_KEY','k')
    monkeypatch.setenv('LLM_EXTRACTION_MODEL','in.openai.gpt-5.6-terra')
    monkeypatch.setenv('VAIDYA_ALLOWED_ORIGINS','https://example.com')
    monkeypatch.delenv('VAIDYA_CLOUD_OPERATIONS_APPROVED',raising=False)
    with pytest.raises(RuntimeError,match='APPROVED'):Settings.load()
    monkeypatch.setenv('VAIDYA_CLOUD_OPERATIONS_APPROVED','true')
    monkeypatch.setenv('ASR_PROVIDER','faster-whisper')  # test legacy local-vetted production settings
    settings=Settings.load()
    assert settings.production is True
    with pytest.raises(PermissionError):settings.allow_real_input()

def test_s3_key_scope_and_private_controls():
    valid='hospital/11111111-1111-1111-1111-111111111111/jobs/22222222-2222-2222-2222-222222222222/draft.docx'
    assert PrivateS3.validate_key(valid)==valid
    with pytest.raises(ValueError):PrivateS3.validate_key('../../etc/passwd')
    with pytest.raises(ValueError):PrivateS3.validate_key('public/draft.docx')

class DummyS3:
    def __init__(self):self.saved={}
    def put_object(self,**kwargs):self.saved[kwargs['Key']]=kwargs
    def get_object(self,**kwargs):
        from io import BytesIO
        return {'Body':BytesIO(self.saved[kwargs['Key']]['Body'])}
    def head_object(self,**kwargs):
        v=self.saved[kwargs['Key']]
        return {'ContentLength':len(v['Body']),'ContentType':v['ContentType'],'ServerSideEncryption':v['ServerSideEncryption']}
    def generate_presigned_post(self,*args,**kwargs):return {'url':'https://private.example','fields':kwargs.get('Fields')}

def test_s3_private_put_get_and_presign():
    key='hospital/11111111-1111-1111-1111-111111111111/jobs/22222222-2222-2222-2222-222222222222/voice.wav'
    c=DummyS3();s=PrivateS3('private','ap-south-1','key-arn',c)
    s.put(key,b'RIFF123','audio/wav')
    assert c.saved[key]['ServerSideEncryption']=='aws:kms'
    assert s.get(key)==b'RIFF123'
    assert s.verified_upload(key,'audio/wav')==7
    assert s.presign_upload(key,'audio/wav')['url'].startswith('https')
    with pytest.raises(ValueError):s.verified_upload(key,'image/png')

def test_document_draft_and_final_are_distinct():
    draft=render_draft('SYN-101','Dr Demo',[{'text':'Synthetic inflammation'}],[],[])
    text=extract_text(draft)
    assert 'REVIEW REQUIRED' not in text or 'DRAFT' in text
    assert 'Synthetic inflammation' in text
    final=render_final('SYN-101','Dr Demo','Synthetic signed content\nSignature: Demo')
    assert 'DOCTOR APPROVED' in extract_text(final)
    assert 'DRAFT — DO NOT RELEASE' not in extract_text(final)

def test_assets_hospital_and_job_scope(context):
    r,b,doc,p=context
    jid,_=r.create_job(doc,b['hospital_id'],p,'private-key','unique-test-idempotency')
    key='hospital/'+b['hospital_id']+'/jobs/'+jid+'/upload.wav'
    aid=r.asset_create(doc,jid,key,'audio','audio/wav')
    with pytest.raises(PermissionError):r.asset_confirm('other-user',jid,aid,42)
    r.asset_confirm(doc,jid,aid,42)
    assert r.asset_list(doc,jid)[0]['uploaded'] is True

def test_queued_until_upload_confirmed(context):
    r,b,doc,p=context
    jid,_=r.create_job(doc,b['hospital_id'],p,'input-ref','upload-gated-unique-key',
                      language_config='ta-en',expect_uploads=True)
    assert r.claim('worker') is None
    assert r.get_job(doc,jid)['status']=='awaiting_uploads'
    key='hospital/'+b['hospital_id']+'/jobs/'+jid+'/uploaded.wav'
    aid=r.asset_create(doc,jid,key,'audio','audio/wav')
    with pytest.raises(ValueError):r.submit_confirmed_uploads(doc,jid)
    r.asset_confirm(doc,jid,aid,123)
    r.submit_confirmed_uploads(doc,jid)
    assert r.claim('worker')['job_id']==jid
    assert r.get_job(doc,jid)['language_config']=='ta-en'


def test_lease_heartbeat_and_abandoned_lease(context):
    r,b,doc,p=context
    jid,_=r.create_job(doc,b['hospital_id'],p,'input-ref','lease-test-idempotency-key')
    t=r.claim('owner',max_attempts=1)
    assert not r.extend_lease(t['id'],'another-worker')
    assert r.extend_lease(t['id'],'owner')
    with r.engine.begin() as c:
        c.execute(update(work).where(work.c.id==t['id']).values(lease_until=now()-timedelta(seconds=5)))
    expired=r.sweep_expired(max_attempts=1)
    assert t['id'] in expired
    assert r.get_job(doc,jid)['status']=='failed'


def test_skill_approval_affects_rendered_draft():
    plain=extract_text(render_draft('SYN-1','Doctor',[{'text':'Dictated content'}],[],[],False))
    changed=extract_text(render_draft('SYN-1','Doctor',[{'text':'Dictated content'}],[],[],True))
    assert 'Doctor signature:' not in plain
    assert 'Doctor signature:' in changed
    assert 'Dictated content' in changed

def test_provider_selection_fail_closed(monkeypatch):
    from production.model_router import get_clinical_extractor,ApprovedCompatibleProvider
    monkeypatch.setenv('LLM_PROVIDER','untrusted')
    with pytest.raises(ValueError):get_clinical_extractor()
    monkeypatch.setenv('LLM_PROVIDER','openai-compatible')
    monkeypatch.setenv('VAIDYA_INFERENCE_ENDPOINT','http://localhost/v1/chat/completions')
    monkeypatch.setenv('VAIDYA_APPROVED_INFERENCE_HOST','localhost')
    with pytest.raises(ValueError):get_clinical_extractor()


def test_approved_compatible_provider_must_have_explicit_host(monkeypatch):
    from production.model_router import ApprovedCompatibleProvider
    monkeypatch.setenv('VAIDYA_APPROVED_INFERENCE_HOST','trusted.example.test')
    monkeypatch.setenv('VAIDYA_PROVIDER_RISK_APPROVED','true')
    with pytest.raises(ValueError):ApprovedCompatibleProvider('https://evil.example.test/v1/chat/completions','test-model','fake')
    monkeypatch.setenv('VAIDYA_PROVIDER_RISK_APPROVED','false')
    with pytest.raises(PermissionError):ApprovedCompatibleProvider('https://trusted.example.test/v1/chat/completions','test-model','fake')


def test_production_sarvam_needs_explicit_vendor_approval(monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://example/db')
    monkeypatch.setenv('FLASK_SECRET_KEY','x'*64)
    monkeypatch.setenv('VAIDYA_S3_BUCKET','private')
    monkeypatch.setenv('VAIDYA_S3_KMS_KEY','sample-kms')
    monkeypatch.setenv('LLM_EXTRACTION_MODEL','approved-model')
    monkeypatch.setenv('VAIDYA_ALLOWED_ORIGINS','https://example.invalid')
    monkeypatch.setenv('VAIDYA_CLOUD_OPERATIONS_APPROVED','true')
    monkeypatch.setenv('ASR_PROVIDER','sarvam')
    monkeypatch.delenv('VAIDYA_SARVAM_CLINICAL_APPROVED',raising=False)
    with pytest.raises(RuntimeError,match='governance approval'):
        Settings.load()
    monkeypatch.setenv('VAIDYA_SARVAM_CLINICAL_APPROVED','true')
    monkeypatch.delenv('SARVAM_API_KEY',raising=False)
    with pytest.raises(RuntimeError,match='credentials'):
        Settings.load()
    monkeypatch.setenv('SARVAM_API_KEY','PRIVATE_TEST_VALUE')
    assert Settings.load().production
