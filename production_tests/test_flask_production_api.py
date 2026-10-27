"""Production API integration suite: runs when Flask is installed (CI/operator machine).

Uses only synthetic identifiers and an isolated SQLite TEST instance. No AWS calls.
"""
import uuid
from pathlib import Path
import pytest
pytest.importorskip('flask')
from production.repository import Repository
from production.settings import Settings
from production.web import build_app
from production.documents import render_draft
from production.storage import PrivateS3

class FakeS3:
    def __init__(self):self.d={}
    def put(self,key,blob,mime):self.d[key]=blob
    def get(self,key,max_bytes=None):return self.d[key]
    def presign_upload(self,key,mime):return {'url':'https://uploads.invalid','fields':{'key':key,'type':mime}}
    def verified_upload(self,key,mime):return 100

@pytest.fixture
def api(tmp_path,monkeypatch):
    monkeypatch.setenv('VAIDYA_TEST_SYNTHETIC','true')
    repo=Repository('sqlite:///'+str(tmp_path/'runtime.db'))
    repo.migrate_for_test()
    ids=repo.bootstrap('Synthetic Hospital','admin@example.invalid','Admin','AdminPassphrase123456')
    doc=repo.add_user(ids['administrator_id'],ids['hospital_id'],'Doctor','doctor@example.invalid','DoctorPassphrase123456','doctor')
    patient=repo.add_patient(doc,ids['hospital_id'],'SYN-1','Synthetic Person')
    settings=Settings(database_url='sqlite:///'+str(tmp_path/'runtime.db'),secret_key='x'*64,aws_region='ap-south-1',
         s3_bucket='fake',s3_kms_key='',bedrock_model='test',allowed_origins=(),production=False,
         allow_clinical_inputs=False,sqlite_for_tests=True)
    blob=FakeS3();app=build_app(settings,repo,blob);app.config['TESTING']=True
    return app.test_client(),repo,ids,doc,patient,blob

def login(client,email,password):
    token=client.get('/api/v1/auth/csrf').json['csrf_token']
    r=client.post('/api/v1/auth/login',json={'email':email,'password':password},
                  headers={'X-CSRF-Token':token})
    assert r.status_code==200
    return r.json['csrf_token']

def test_unauthenticated_denied(api):
    c,*_=api
    assert c.get('/api/v1/patients').status_code==401
    assert c.get('/health/live').json['status']=='ok'
    assert c.get('/health/ready').json['clinical_use_authorized'] is False
    assert c.post('/api/v1/report-jobs',json={}).status_code==401

def test_csrf_enforced_on_login_and_creation(api):
    c,r,ids,doc,p,blob=api
    assert c.post('/api/v1/auth/login',json={'email':'doctor@example.invalid','password':'DoctorPassphrase123456'}).status_code==403
    login(c,'doctor@example.invalid','DoctorPassphrase123456')
    assert c.post('/api/v1/patients',json={'reference':'SYN-2','display_name':'Synthetic 2'}).status_code==403

def test_full_synthetic_api_flow_to_doctor_approval(api):
    c,r,ids,doc,p,blob=api
    token=login(c,'doctor@example.invalid','DoctorPassphrase123456')
    # Production rejects typed transcripts and requires an audio upload.
    rejected=c.post('/api/v1/report-jobs',json={'patient_id':p,'transcript':'NOT_ACCEPTED','language_config':'en'},
        headers={'X-CSRF-Token':token,'Idempotency-Key':'reject-text-unique-transaction'})
    assert rejected.status_code==400
    resp=c.post('/api/v1/report-jobs',json={'patient_id':p,'expect_uploads':True,'language_config':'en'},
        headers={'X-CSRF-Token':token,'Idempotency-Key':'synthetic-unique-transaction'})
    assert resp.status_code==202
    jid=resp.json['job_id']
    duplicate=c.post('/api/v1/report-jobs',json={'patient_id':p,'expect_uploads':True},
        headers={'X-CSRF-Token':token,'Idempotency-Key':'synthetic-unique-transaction'})
    assert duplicate.json['job_id']==jid
    # Confirm actual audio-asset metadata before queueing. No transcript submitted.
    upload=c.post(f'/api/v1/report-jobs/{jid}/uploads',json={'kind':'audio','content_type':'audio/ogg'},
        headers={'X-CSRF-Token':token})
    assert upload.status_code==201
    asset_id=upload.json['asset_id']
    assert c.post(f'/api/v1/report-jobs/{jid}/uploads/{asset_id}/confirm',
        headers={'X-CSRF-Token':token}).status_code==200
    assert c.post(f'/api/v1/report-jobs/{jid}/uploads/complete',
        headers={'X-CSRF-Token':token}).status_code==202
    # Stub only the worker's result for independent API routing/approval tests.
    key='hospital/'+ids['hospital_id']+'/jobs/'+jid+'/draft.docx'
    blob.put(key,render_draft('SYN-1','Doctor',[{'text':'Synthetic dictated tissue inflammation'}],[]),'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    r.set_draft(jid,key,'mocked-evaluation-model')
    assert c.get('/api/v1/report-jobs/'+jid+'/draft').status_code==200
    approved=c.post('/api/v1/report-jobs/'+jid+'/approve',json={'final_text':'Synthetic approved content\nSignature: Test','attest':True},headers={'X-CSRF-Token':token})
    assert approved.status_code==200
    assert r.get_job(doc,jid)['status']=='approved'
    second=c.post('/api/v1/report-jobs/'+jid+'/approve',json={'final_text':'another','attest':True},headers={'X-CSRF-Token':token})
    assert second.status_code==409

def test_admin_has_no_doctor_creation_permissions(api):
    c,r,ids,doc,p,blob=api
    token=login(c,'admin@example.invalid','AdminPassphrase123456')
    assert c.get('/api/v1/patients').status_code==403
    assert c.get('/api/v1/admin/learnings').status_code==200
