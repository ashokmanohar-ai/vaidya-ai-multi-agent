"""Authenticated HTTP API for a future controlled clinical-service deployment.

Default: read-only operational service; clinical data processing is disabled until
an explicit operator approval and external clinical/privacy authorization.
"""
from __future__ import annotations
import os
import secrets
import uuid
import hashlib
from functools import wraps
from flask import Flask,request,jsonify,session,abort,Response,send_from_directory
from sqlalchemy import select
from .settings import Settings
from .repository import Repository,ident
from .storage import PrivateS3
from .tables import patients,jobs,learnings,skills
from .documents import render_final


def build_app(settings=None,repo=None,storage=None):
    settings=settings or Settings.load()
    repo=repo or Repository(settings.database_url)
    app=Flask(__name__,static_folder='static',static_url_path='/console-assets')
    app.config.update(SECRET_KEY=settings.secret_key,SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=settings.production,SESSION_COOKIE_SAMESITE='Strict',
        PERMANENT_SESSION_LIFETIME=900,MAX_CONTENT_LENGTH=256*1024)

    def client_storage():
        return storage if storage is not None else PrivateS3(settings.s3_bucket,settings.aws_region,settings.s3_kms_key)

    @app.after_request
    def safety_headers(r):
        r.headers['X-Frame-Options']='DENY'
        r.headers['X-Content-Type-Options']='nosniff'
        r.headers['Cache-Control']='no-store'
        r.headers['Referrer-Policy']='no-referrer'
        r.headers['Content-Security-Policy']=("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self' "
            + settings.s3_upload_origin + "; img-src 'self'; frame-ancestors 'none'")
        r.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains' if settings.production else ''
        return r

    def auth(role=None):
        def dec(fn):
            @wraps(fn)
            def inner(*args,**kwargs):
                uid=session.get('uid')
                actor=repo.account(uid) if uid else None
                if not actor:abort(401)
                if role and actor['role']!=role:abort(403)
                return fn(actor,*args,**kwargs)
            return inner
        return dec

    def csrf():
        origin=request.headers.get('Origin')
        if settings.production and origin and origin.rstrip('/') not in settings.allowed_origins:
            abort(403,'Request origin not permitted')
        sent=request.headers.get('X-CSRF-Token','')
        if not secrets.compare_digest(sent,session.get('_csrf','')) or not sent:
            abort(403,'CSRF token required')

    def clinical_gate():
        if settings.sqlite_for_tests and os.getenv('VAIDYA_TEST_SYNTHETIC')=='true':return
        settings.allow_real_input()

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(413)
    def expected(e):return jsonify(error=e.name,code=e.code),e.code

    @app.get('/')
    @app.get('/console')
    def portal():return send_from_directory('static','index.html')

    @app.get('/health/live')
    def health():return jsonify(service='vaidya-ai-production-engineering',status='ok')

    @app.get('/health/ready')
    def ready():
        try:
            with repo.engine.connect() as c:c.exec_driver_sql('SELECT 1')
            return jsonify(status='ready',clinical_use_authorized=False,
                           clinical_inputs_enabled=settings.allow_clinical_inputs),200
        except Exception:
            return jsonify(status='not_ready',clinical_use_authorized=False),503

    @app.get('/api/v1/auth/csrf')
    def csrf_start():
        session['_csrf']=secrets.token_urlsafe(32)
        return jsonify(csrf_token=session['_csrf'])

    @app.post('/api/v1/auth/login')
    def login():
        csrf()
        body=request.get_json(silent=True) or {}
        email=str(body.get('email',''))[:255]
        password=str(body.get('password',''))[:1024]
        actor=repo.authenticate(email,password)
        if not actor:abort(401)
        session.clear();session['uid']=actor['id'];session['_csrf']=secrets.token_urlsafe(32)
        session.permanent=True
        repo.audit(actor['id'],actor['hospital_id'],'login','user',actor['id'])
        return jsonify(role=actor['role'],name=actor['name'],csrf_token=session['_csrf'])

    @app.post('/api/v1/auth/logout')
    @auth()
    def logout(actor):
        csrf();repo.audit(actor['id'],actor['hospital_id'],'logout','user',actor['id'])
        session.clear();return jsonify(status='signed_out')

    @app.get('/api/v1/auth/me')
    @auth()
    def me(actor):return jsonify(id=actor['id'],name=actor['name'],role=actor['role'])

    @app.get('/api/v1/patients')
    @auth('doctor')
    def list_patients(actor):return jsonify(patients=repo.patient_list(actor['id'],actor['hospital_id']))

    @app.post('/api/v1/patients')
    @auth('doctor')
    def add_patient(actor):
        csrf();clinical_gate();body=request.get_json(silent=True) or {}
        try:
            p=repo.add_patient(actor['id'],actor['hospital_id'],str(body.get('reference','')),
                              str(body.get('display_name','')))
        except ValueError:abort(400)
        return jsonify(id=p),201

    @app.post('/api/v1/report-jobs')
    @auth('doctor')
    def submit_job(actor):
        csrf();clinical_gate();body=request.get_json(silent=True) or {}
        patient=str(body.get('patient_id',''))
        # Production accepts AUDIO only; no typed, sample or synthetic ASR substitutes.
        content = body.get('transcript')
        token=request.headers.get('Idempotency-Key','')
        expect_uploads=body.get('expect_uploads') is True
        if content not in (None, '') or not expect_uploads or not 12<=len(token)<=100:
            abort(400,'Audio upload required; typed transcripts are not accepted')
        repo.authorized_patient(actor['id'],actor['hospital_id'],patient)
        existing=repo.get_idempotent_job(actor['id'],token)
        if existing:return jsonify(job_id=existing,status='existing'),200
        jid=ident()
        key=f"hospital/{actor['hospital_id']}/jobs/{jid}/input.txt"
        client_storage().put(key,content.encode('utf-8'),'text/plain')
        try:
            job,created=repo.create_job(actor['id'],actor['hospital_id'],patient,key,token,job_id=jid,
                language_config=str(body.get('language_config','en')),expect_uploads=expect_uploads)
        except ValueError:abort(400)
        return jsonify(job_id=job,status='awaiting_uploads' if body.get('expect_uploads') is True else 'queued' if created else 'existing'),202 if created else 200

    @app.get('/api/v1/report-jobs/<job_id>')
    @auth('doctor')
    def get_job(actor,job_id):
        try:j=repo.get_job(actor['id'],job_id)
        except PermissionError:abort(404)
        return jsonify(job_id=job_id,status=j['status'],model_id=j['model_id'],
                       doctor_review_required=j['status']=='draft_ready')

    @app.post('/api/v1/report-jobs/<job_id>/uploads')
    @auth('doctor')
    def presign(actor,job_id):
        csrf();clinical_gate()
        try:job=repo.get_job(actor['id'],job_id)
        except PermissionError:abort(404)
        body=request.get_json(silent=True) or {}
        kind=str(body.get('kind',''));mime=str(body.get('content_type',''))
        exts={'audio/wav':'.wav','audio/mpeg':'.mp3','audio/webm':'.webm',
            'audio/mp4':'.m4a','audio/ogg':'.ogg','image/png':'.png','image/jpeg':'.jpg'}
        ext=exts.get(mime)
        if ext is None:abort(400)
        key=f"hospital/{job['hospital_id']}/jobs/{job_id}/{uuid.uuid4().hex}{ext}"
        try:
            aid=repo.asset_create(actor['id'],job_id,key,kind,mime)
            signed=client_storage().presign_upload(key,mime)
        except ValueError:abort(400)
        return jsonify(asset_id=aid,upload=signed),201

    @app.post('/api/v1/report-jobs/<job_id>/uploads/<asset_id>/confirm')
    @auth('doctor')
    def confirm(actor,job_id,asset_id):
        csrf();clinical_gate()
        try:
            item=next((x for x in repo.asset_list(actor['id'],job_id) if x['id']==asset_id),None)
        except PermissionError:abort(404)
        if not item:abort(404)
        try:
            size=client_storage().verified_upload(item['object_key'],item['content_type'])
            repo.asset_confirm(actor['id'],job_id,asset_id,size)
        except ValueError:abort(400)
        return jsonify(status='confirmed')

    @app.post('/api/v1/report-jobs/<job_id>/uploads/complete')
    @auth('doctor')
    def submit_uploads(actor,job_id):
        csrf();clinical_gate()
        try:repo.submit_confirmed_uploads(actor['id'],job_id)
        except PermissionError:abort(404)
        except ValueError:abort(409)
        return jsonify(status='queued'),202

    @app.get('/api/v1/report-jobs/<job_id>/draft')
    @auth('doctor')
    def draft(actor,job_id):
        try:j=repo.get_job(actor['id'],job_id)
        except PermissionError:abort(404)
        if not j['draft_key']:abort(404)
        return Response(client_storage().get(j['draft_key']),mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        headers={'Content-Disposition':'attachment; filename="draft.docx"'})

    @app.post('/api/v1/report-jobs/<job_id>/approve')
    @auth('doctor')
    def approve(actor,job_id):
        csrf();clinical_gate()
        try:j=repo.get_job(actor['id'],job_id)
        except PermissionError:abort(404)
        body=request.get_json(silent=True) or {}
        text=body.get('final_text','')
        if body.get('attest') is not True or not isinstance(text,str) or not text.strip():abort(400)
        if j['status']!='draft_ready':abort(409)
        with repo.engine.connect() as c:
            p=c.execute(select(patients).where(patients.c.id==j['patient_id'])).mappings().one()
        artifact=render_final(p['reference'],actor['name'],text)
        key=f"hospital/{j['hospital_id']}/jobs/{job_id}/approved.docx"
        client_storage().put(key,artifact,'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        try:repo.approve(actor['id'],job_id,key,hashlib.sha256(artifact).hexdigest())
        except ValueError:abort(409)
        return jsonify(status='approved',learning_queued=True),200

    @app.get('/api/v1/admin/learnings')
    @auth('admin')
    def learning_list(actor):return jsonify(learnings=repo.learning_candidates(actor['id']))

    @app.post('/api/v1/admin/learnings/<learning_id>/decision')
    @auth('admin')
    def learning_decision(actor,learning_id):
        csrf();body=request.get_json(silent=True) or {}
        decision=body.get('decision')
        try:
            # The graph's interrupt is first prepared (on the server), then resumed
            # through this authenticated control; it never trusts a model as approver.
            from .graph import ProductionGraph
            graph=ProductionGraph(repo,client_storage(),settings.database_url)
            snapshot=graph.checkpoint('clinical:approval:'+learning_id)
            if not snapshot['pending_nodes']:
                graph.start_review(learning_id)
            graph.decide(learning_id,actor['id'],decision)
        except (ValueError,PermissionError):abort(409)
        return jsonify(status=decision)
    return app
