"""Vaidya AI Flask leadership pilot: SYNTHETIC DEMO DATA ONLY.

Production clinical processing requires a separate data protection, security and
clinical validation workstream; this sample is explicitly not production-ready.
"""
from __future__ import annotations
import json
import os
import secrets
import uuid
from datetime import datetime
from pathlib import Path
from functools import wraps

from flask import Flask, request, redirect, url_for, session, render_template, jsonify, send_file, abort, flash
from werkzeug.utils import secure_filename
from PIL import Image

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

from vaidya.database import Database, utcnow, verify_password
from vaidya.providers import get_provider, bedrock_settings
from vaidya.multi_agent import GraphRuntime
from vaidya.reports import render_docx, final_docx, structured_final_docx
from vaidya.learning import create_seed_learning
from vaidya.media import save_voice_notes
from vaidya.audio import asr_status
from vaidya.clinical_review import final_document_issues, assess_report
from vaidya.structured_review import candidates, validate_fields, formatted_report, reconcile_minor_name_spelling, verified_audio_patient

BASE=Path(__file__).resolve().parent
app=Flask(__name__)
app.secret_key=os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
app.config.update(MAX_CONTENT_LENGTH=80*1024*1024,
    SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('APP_ENV')=='production')
DATA=Path(os.getenv('VAIDYA_DATA_DIR',str(BASE/'instance')))
DB=Database(DATA/'vaidya.sqlite3')
DEMO=os.getenv('DEMO_MODE','').lower() in ('1','true','yes')
AUDIO_ONLY=os.getenv('AUDIO_ONLY_MODE','').lower() in ('1','true','yes')
if DEMO and (os.getenv('APP_ENV','').lower() in ('production','preview') or os.getenv('VERCEL') or os.getenv('VERCEL_ENV')):
    raise RuntimeError('Synthetic demo must not be exposed as a Vercel production/preview application')
_runtime = None

def graph_runtime():
    global _runtime
    if _runtime is None:
        _runtime = GraphRuntime(DB, DATA)
    return _runtime


def ensure_demo():
    if not DEMO:abort(404)


def csrf_token():
    if '_csrf' not in session: session['_csrf']=secrets.token_hex(24)
    return session['_csrf']
app.jinja_env.globals['csrf_token']=csrf_token
app.jinja_env.globals['audio_only_mode']=lambda:AUDIO_ONLY


def check_csrf():
    from hmac import compare_digest
    supplied=request.form.get('_csrf') or request.headers.get('X-CSRF-Token')
    if not supplied or not compare_digest(str(supplied),str(session.get('_csrf',''))):abort(400,'Invalid form security token')


def user():
    uid=session.get('uid')
    return DB.query('SELECT id,email,name,role,hospital_id FROM users WHERE id=?',(uid,),one=True) if uid else None


def required_role(role=None):
    def dec(fn):
        @wraps(fn)
        def guard(*a,**k):
            ensure_demo()
            u=user()
            if not u:
                if request.path.startswith('/api/'):return jsonify(error='Authentication required'),401
                return redirect(url_for('login'))
            if role and u['role']!=role:abort(403)
            return fn(*a,**k)
        return guard
    return dec


@app.after_request
def security_headers(r):
    r.headers['X-Content-Type-Options']='nosniff'
    r.headers['X-Frame-Options']='DENY'
    r.headers['Referrer-Policy']='no-referrer'
    r.headers['Cache-Control']='no-store'
    r.headers['Content-Security-Policy']=("default-src 'self'; style-src 'self' 'unsafe-inline'; "
       "script-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
    return r


@app.errorhandler(413)
def too_large(e):return render_template('message.html',title='Upload too large',message='Files exceed the 80 MB local-demo request limit.',who=user()),413


@app.get('/health/live')
def live():return jsonify(status='ok',service='vaidya-ai',mode='synthetic-demo' if DEMO else 'public-foundation')


@app.get('/health/ready')
def ready():
    cfg=bedrock_settings()
    return jsonify(status='demo_ready' if DEMO else 'foundation_only',clinical_ready=False,
                   demo=DEMO,transcription_available=asr_status().get('ready',False),asr=asr_status(),bedrock_configured=(cfg['provider']=='bedrock' and (cfg['credential_configured'] or cfg['aws_profile_configured'] or cfg['aws_static_keys_configured']) and cfg['remote_opt_in']),
                   bedrock_connection_tested=False,graph_required=DEMO)


@app.get('/api/v1/status')
def api_status():
    return jsonify(product='Vaidya AI',clinical_ready=False,demo=DEMO,
       providers=['demo-rules','bedrock-optional'],asr=asr_status(),workflow='durable LangGraph orchestrator + pathology and learner subgraphs')


@app.get('/')
def index():
    if not DEMO:return render_template('landing.html')
    u=user()
    if u:return redirect(url_for('admin_dashboard') if u['role']=='admin' else url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login',methods=['GET','POST'])
def login():
    ensure_demo()
    if request.method=='POST':
        check_csrf()
        email=request.form.get('email','').strip().lower()
        p=request.form.get('password','')
        u=DB.query('SELECT * FROM users WHERE email=?',(email,),one=True)
        if u and verify_password(p,u['password_hash']):
            session.clear();session['uid']=u['id'];session['_csrf']=secrets.token_hex(24)
            DB.audit(u['id'],'login','user',u['id'])
            return redirect(url_for('admin_dashboard') if u['role']=='admin' else url_for('dashboard'))
        flash('Incorrect email or password. Use the synthetic demo credentials.')
    return render_template('login.html',who=None)


@app.post('/logout')
def logout():
    check_csrf();uid=session.get('uid')
    if uid:DB.audit(uid,'logout','user',uid)
    session.clear()
    return redirect(url_for('login'))


@app.get('/dashboard')
@required_role('doctor')
def dashboard():
    u=user()
    jobs=DB.query('SELECT j.id,j.created_at,j.status,j.provider,j.model,p.name AS patient,p.code '
       'FROM jobs j JOIN patients p ON p.id=j.patient_id WHERE j.doctor_id=? ORDER BY j.created_at DESC LIMIT 15',(u['id'],))
    counts=DB.query('SELECT status,COUNT(*) n FROM jobs WHERE doctor_id=? GROUP BY status',(u['id'],))
    return render_template('dashboard.html',who=u,jobs=jobs,stats={r['status']:r['n'] for r in counts})


@app.get('/reports/new')
@required_role('doctor')
def new_report():
    u=user()
    pts=DB.query('SELECT * FROM patients WHERE hospital_id=? ORDER BY code',(u['hospital_id'],)) if not AUDIO_ONLY else []
    return render_template('new_report.html',who=u,patients=pts,asr=asr_status(),audio_only=AUDIO_ONLY)


def read_images(job_id):
    images=[]
    for idx,f in enumerate(request.files.getlist('images')):
        if not f or not f.filename:continue
        if idx>=5:raise ValueError('Maximum five images per report')
        raw=f.read(5*1024*1024+1)
        if len(raw)>5*1024*1024:raise ValueError('Each image must be less than 5 MB')
        from io import BytesIO
        try:
            with Image.open(BytesIO(raw)) as im:
                if im.format not in ('PNG','JPEG'):raise ValueError('Only PNG or JPEG images are accepted')
                im.verify()
        except Exception as exc:raise ValueError('Invalid image file') from exc
        ext='.png' if raw[:8]==b'\x89PNG\r\n\x1a\n' else '.jpg'
        target=DATA/'uploads'/f'{job_id}-{idx}{ext}'
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw)
        images.append(str(target))
    return images


@app.post('/patients/create')
@required_role('doctor')
def create_synthetic_patient():
    """Explicitly synthetic patient entry. Never derive identity from untrusted ASR."""
    import re
    check_csrf()
    if AUDIO_ONLY:abort(404,'Manual patient registration is not available in audio-only mode')
    u=user()
    if request.form.get('synthetic_only')!='yes':
        abort(400,'Only synthetic demonstration patients are permitted')
    code=request.form.get('code','').strip().upper()
    name=request.form.get('name','').strip()
    age_raw=request.form.get('age','').strip()
    sex=request.form.get('sex','').strip()
    if not re.fullmatch(r'DEMO-[A-Z0-9-]{2,24}',code):
        abort(400,'Synthetic code must start DEMO- followed by letters/numbers')
    if not (2<=len(name)<=80) or any(ord(char)<32 for char in name) or not re.fullmatch(r"[^\W\d_][\w .'-]{1,79}",name,re.UNICODE):
        abort(400,'Enter a valid synthetic display name')
    if not age_raw.isascii() or not age_raw.isdigit() or not (0<=int(age_raw)<=120):
        abort(400,'Enter age 0–120')
    if sex not in ('Female','Male','Other'):
        abort(400,'Select a valid sex value')
    try:
        patient_id=DB.execute('INSERT INTO patients(code,name,age,sex,hospital_id) VALUES(?,?,?,?,?)',
                              (code,name,int(age_raw),sex,u['hospital_id']))
    except __import__('sqlite3').IntegrityError:
        abort(409,'A synthetic patient with that reference already exists')
    DB.audit(u['id'],'create_synthetic_patient','patient',patient_id)
    flash('Synthetic patient created. Choose this record when generating a new draft.')
    return redirect(url_for('new_report'))


@app.post('/reports/create')
@required_role('doctor')
def create_report():
    check_csrf();u=user()
    # Audio-only flow derives an unverified patient candidate after live ASR.
    # Browser-provided patient IDs must not influence its clinical report.
    if AUDIO_ONLY:
        if request.form.get('patient_id'):
            abort(400,'Audio-only reports do not accept a manually selected patient')
        patient=None
    else:
        patient_id=request.form.get('patient_id','')
        patient=DB.query('SELECT * FROM patients WHERE id=? AND hospital_id=?',(patient_id,u['hospital_id']),one=True)
        if not patient:abort(403)
    transcript=request.form.get('transcript','').strip()
    audio_files=[f for f in request.files.getlist('audio_notes') if f and f.filename]
    if AUDIO_ONLY and transcript:
        abort(400,'Audio-only workflow rejects typed and sample transcripts')
    if AUDIO_ONLY and not audio_files:
        abort(400,'Upload a voice note. No fallback transcript is allowed')
    if (not transcript and not audio_files) or len(transcript)>16000:
        abort(400,'Audio/transcript missing or too long')
    if audio_files and not asr_status().get('ready'):
        abort(503,'Configured ASR provider not ready; check API key, SDK and approval configuration')
    language_config=request.form.get('language_config','ta-en')
    if language_config not in ('ta-en','en','ta'):abort(400,'Unsupported language')
    job_id=str(uuid.uuid4())
    images=[]
    audio=[]
    successful=False
    try:
        images=read_images(job_id)
        audio=save_voice_notes(audio_files,DATA,job_id)
        result=graph_runtime().generate(job_id=job_id,doctor_id=u['id'],patient_id=patient['id'] if patient else None,
              hospital_id=u['hospital_id'],transcript=transcript,images=images,
              audio=audio,language_config=language_config)
        DB.audit(u['id'],'generate_draft','job',job_id)
        successful=True
        return redirect(url_for('review_report',job_id=job_id))
    except (ValueError,RuntimeError,PermissionError) as e:
        flash('Audio transcription or report generation failed: '+str(e)[:200]);return redirect(url_for('new_report'))
    except Exception:
        app.logger.exception('Report creation failed for synthetic job %s',job_id)
        flash('Unable to generate draft. Check developer logs and model configuration.')
        return redirect(url_for('new_report'))
    finally:
        if not successful:
            for private_path in audio + images:
                Path(private_path).unlink(missing_ok=True)
            if AUDIO_ONLY:
                # Remove orphaned ASR candidates from unsuccessful jobs only.
                # A successfully persisted job always retains its linked identity.
                with DB.connect() as conn:
                    conn.execute('DELETE FROM patients WHERE code=? AND hospital_id=? '
                        'AND NOT EXISTS(SELECT 1 FROM jobs WHERE jobs.patient_id=patients.id)',
                        ('AUDIO-'+job_id,u['hospital_id']))


def authorized_job(job_id):
    u=user()
    j=DB.query('SELECT j.*,p.code AS patient_code,p.name AS patient_name FROM jobs j '
          'JOIN patients p ON p.id=j.patient_id WHERE j.id=? AND j.hospital_id=? AND j.doctor_id=?',
          (job_id,u['hospital_id'],u['id']),one=True)
    if not j:abort(404)
    return j


def job_safety_assessment(job):
    """Reassess legacy drafts lacking the new validation snapshot.

    The original pre-update jobs did not persist source reconciliation.
    Rebuilding it also prevents API users from bypassing the review-page UI.
    """
    saved = json.loads(job.get('validation_json') or '{}')
    if saved and 'blocking_issues' in saved and 'has_audio' in saved:
        return saved
    patient = DB.query('SELECT * FROM patients WHERE id=? AND hospital_id=?',
                       (job['patient_id'], job['hospital_id']), one=True)
    if not patient:abort(409,'Patient record no longer available')
    audio_present = DB.query('SELECT id FROM job_inputs WHERE job_id=? AND kind=? LIMIT 1',
                             (job['id'],'audio'),one=True) is not None
    result = assess_report(patient,job['original_transcript'],
                           json.loads(job['findings_json']),json.loads(job['instruction_json']),
                           audio_present=audio_present)
    DB.execute('UPDATE jobs SET validation_json=? WHERE id=?',
               (json.dumps(result,ensure_ascii=False),job['id']))
    return result


@app.get('/reports/<job_id>')
@required_role('doctor')
def review_report(job_id):
    j=authorized_job(job_id)
    trace=DB.query('SELECT agent,stage,status,created_at FROM workflow_events WHERE job_id=? ORDER BY id',(job_id,))
    checkpoint=graph_runtime().checkpoint_summary('vaidya:report:'+job_id)
    audio_count=len(DB.query("SELECT id FROM job_inputs WHERE job_id=? AND kind='audio'",(job_id,)))
    asr_inputs=DB.query("SELECT seq,metadata_json FROM job_inputs WHERE job_id=? AND kind='audio' ORDER BY seq",(job_id,))
    assessment=job_safety_assessment(j)
    review_metadata=json.loads(j.get('review_json') or '{}')
    return render_template('review.html',who=user(),job=j,trace=trace,checkpoint=checkpoint,
        audio_identity=str(j['patient_code']).startswith('AUDIO-'),
        assessment=assessment, review_metadata=review_metadata, field_candidates=candidates(assessment), audio_count=audio_count,
        asr_inputs=[json.loads(x['metadata_json']) for x in asr_inputs],
        findings=json.loads(j['findings_json']),instructions=json.loads(j['instruction_json']))


@app.get('/reports/<job_id>/download')
@required_role('doctor')
def download(job_id):
    j=authorized_job(job_id)
    path=DATA/'reports'/j['draft_filename']
    if not path.exists():abort(404)
    DB.audit(user()['id'],'download_draft','job',job_id)
    return send_file(path,as_attachment=True,download_name=f'VAIDYA_DRAFT_{job_id[:8]}.docx')


@app.post('/reports/<job_id>/approve-structured')
@required_role('doctor')
def approve_structured_report(job_id):
    """Field-by-field verified synthetic report; do not trust ASR or browser checks."""
    check_csrf()
    j=authorized_job(job_id)
    if j['status']!='draft_ready':abort(409,'Job already finalized')
    assessment=job_safety_assessment(j)
    patient=DB.query('SELECT * FROM patients WHERE id=? AND hospital_id=?',
                     (j['patient_id'],j['hospital_id']),one=True)
    hospital=DB.query('SELECT * FROM hospitals WHERE id=?',(j['hospital_id'],),one=True)
    if not patient or not hospital:abort(409,'Patient/hospital record no longer exists')
    audio_identity=str(patient['code']).startswith('AUDIO-')
    if audio_identity:
        reviewed_patient,identity_errors,name_resolution_note=verified_audio_patient(request.form,candidate=patient)
        # This patient was created only from ASR, never selected from unrelated records.
        # Document any manual correction; the clinician attests to source audio.
        effective_assessment=dict(assessment)
        effective_assessment['blocking_issues']=list(assessment.get('blocking_issues') or [])
    else:
        reviewed_patient=dict(patient)
        identity_errors=[]
        effective_assessment,name_resolution_note=reconcile_minor_name_spelling(assessment,patient,request.form)
    fields,errors=validate_fields(request.form,assessment=effective_assessment,patient=reviewed_patient)
    errors=identity_errors+errors
    if errors:abort(409,'Approval blocked: '+errors[0][:260])
    reviewed_text=formatted_report(reviewed_patient,fields)
    issues=final_document_issues(reviewed_text,effective_assessment)
    if issues:abort(409,'Approval blocked: '+issues[0][:260])
    now=utcnow();uid=user()['id']
    final_path=DATA/'reports'/f'{job_id}-doctor-final.docx'
    staged_path=DATA/'reports'/f'{job_id}-{secrets.token_hex(8)}-staged-final.docx'
    record={'version':1,'source':'manual_verified_fields','reviewed_at_utc':now,
            'reviewed_by_user_id':uid,'fields':fields,'original_asr_immutable':True,
            'name_resolution_note':name_resolution_note,
            'asr_patient_candidate':{'name':patient.get('name'),'age':patient.get('age'),'sex':patient.get('sex')},
            'patient_after_source_review':{'name':reviewed_patient['name'],'age':reviewed_patient['age'],'sex':reviewed_patient['sex']}}
    try:
        structured_final_docx(fields,j,reviewed_patient,hospital,staged_path)
        with DB.connect() as conn:
            changed=conn.execute('UPDATE jobs SET final_text=?, review_json=?, status=?,approved_at=?,approved_by=? '
                  'WHERE id=? AND status=?',(reviewed_text,json.dumps(record,ensure_ascii=False),
                   'approved',now,uid,job_id,'draft_ready')).rowcount
            if changed!=1:abort(409,'Job was finalized by another request')
            if audio_identity:
                conn.execute('UPDATE patients SET name=?,age=?,sex=? WHERE id=? AND hospital_id=?',
                             (reviewed_patient['name'],reviewed_patient['age'],reviewed_patient['sex'],
                              patient['id'],j['hospital_id']))
            os.replace(staged_path,final_path)
    finally:
        staged_path.unlink(missing_ok=True)
    DB.audit(uid,'approve_structured_synthetic_final','job',job_id)
    try:
        graph_runtime().complete_doctor_review(job_id,uid)
        graph_runtime().analyze(job_id)
    except Exception:
        app.logger.exception('Structured final approved; LangGraph learner resume pending for %s',job_id)
        flash('Final DOCX approved, but LangGraph learning requires retry.')
    return redirect(url_for('review_report',job_id=job_id))


@app.post('/reports/<job_id>/approve')
@required_role('doctor')
def approve_report(job_id):
    check_csrf();j=authorized_job(job_id)
    if j['status']!='draft_ready':abort(409,'Job already finalized')
    text=request.form.get('final_text','').strip()
    if not text or len(text)>25000:abort(400,'Final content invalid')
    if request.form.get('attest')!='yes':abort(400,'Clinician review attestation required')
    assessment=job_safety_assessment(j)
    if assessment.get('has_audio'):
        abort(409,'Audio-based drafts require per-field structured review; use the verified-fields form')
    problems=final_document_issues(text,assessment)
    if problems:
        abort(409, 'Approval blocked: '+problems[0][:250])
    # A one-word or blanked-out report is not a meaningful clinician final.
    # This minimum is only a basic documentation safeguard, not proof of
    # clinical correctness or source fidelity.
    if len(text) < 40:
        abort(400, 'Final report is too short to be a substantive reviewed document')
    if assessment.get('has_audio'):
        for check in ('verified_audio','verified_identity','verified_numbers','verified_negations','verified_instructions'):
            if request.form.get(check)!='yes':
                abort(400, 'Audio-based draft requires explicit verification: '+check)
    uid=user()['id'];now=utcnow()
    patient=DB.query('SELECT * FROM patients WHERE id=?',(j['patient_id'],),one=True)
    hospital=DB.query('SELECT * FROM hospitals WHERE id=?',(j['hospital_id'],),one=True)
    final_path=DATA/'reports'/f'{job_id}-doctor-final.docx'
    staged_path=DATA/'reports'/f'{job_id}-{secrets.token_hex(8)}-staged-final.docx'
    # Render to a unique private staging file first. A concurrent/retried
    # approval must never replace the approved artifact with the LOSING text.
    # Under the SQLite write transaction, claim draft_ready and atomically
    # publish the document; failure rolls back the status transition.
    try:
        final_docx(text,j,patient,hospital,staged_path)
        with DB.connect() as c:
            updated=c.execute('UPDATE jobs SET final_text=?, status=?, approved_at=?, approved_by=? '
                              'WHERE id=? AND status=?',(text,'approved',now,uid,job_id,'draft_ready')).rowcount
            if updated!=1:abort(409,'Job was finalized by another request')
            os.replace(staged_path,final_path)
    finally:
        staged_path.unlink(missing_ok=True)
    DB.audit(uid,'approve_final','job',job_id)
    try:
        graph_runtime().complete_doctor_review(job_id,uid)
        result=graph_runtime().analyze(job_id)
        outcome=result.get('learning_outcome')
        # Prepare a durable, interrupted admin-review thread for any new suggestion.
        if outcome and outcome.get('evidence_count',0)>=5:
            candidate=DB.query('SELECT id,status FROM learnings WHERE pattern_key=?',
                         (outcome['pattern'],),one=True)
            if candidate and candidate['status']=='suggested':
                graph_runtime().prepare_learning_review(candidate['id'])
        flash('Synthetic report finalized. The LangGraph Learner analyzed the corrections.' if outcome
              else 'Synthetic report finalized; no correction detected.')
    except Exception:
        app.logger.exception('Approved report %s: learning execution pending retry',job_id)
        flash('Doctor final approved. Learning analysis needs an administrator retry.')
    return redirect(url_for('review_report',job_id=job_id))


@app.get('/reports/<job_id>/final-download')
@required_role('doctor')
def final_download(job_id):
    j=authorized_job(job_id)
    if j['status']!='approved':abort(404)
    path=DATA/'reports'/f'{job_id}-doctor-final.docx'
    if not path.exists():abort(404)
    DB.audit(user()['id'],'download_final','job',job_id)
    return send_file(path,as_attachment=True,download_name=f'VAIDYA_SYNTHETIC_FINAL_{job_id[:8]}.docx')


@app.get('/api/v1/jobs')
@required_role('doctor')
def api_jobs():
    u=user();rows=DB.query('SELECT id,created_at,provider,model,status FROM jobs WHERE doctor_id=? AND hospital_id=? ORDER BY created_at DESC',
          (u['id'],u['hospital_id']))
    return jsonify(jobs=rows)


@app.get('/api/v1/jobs/<job_id>')
@required_role('doctor')
def api_job(job_id):
    j=authorized_job(job_id)
    return jsonify(job_id=j['id'],status=j['status'],provider=j['provider'],model=j['model'],
                   created_at=j['created_at'],audio_note_count=len(DB.query("SELECT id FROM job_inputs WHERE job_id=? AND kind='audio'",(job_id,))),
                   doctor_review_required=j['status']=='draft_ready',
                   graph=graph_runtime().checkpoint_summary('vaidya:report:'+job_id),
                   stages=graph_runtime().trace(job_id))


@app.get('/api/v1/jobs/<job_id>/graph')
@required_role('doctor')
def api_graph(job_id):
    authorized_job(job_id)
    return jsonify(checkpoint=graph_runtime().checkpoint_summary('vaidya:report:'+job_id),
                   stages=graph_runtime().trace(job_id))


@app.post('/reports/<job_id>/resume')
@required_role('doctor')
def resume_approved_job(job_id):
    check_csrf()
    j=authorized_job(job_id)
    if j['status']!='approved':abort(409,'This job has not received doctor approval')
    try:
        graph_runtime().complete_doctor_review(job_id,user()['id'])
        result=graph_runtime().analyze(job_id)
        outcome=result.get('learning_outcome')
        if outcome and outcome.get('evidence_count',0)>=5:
            candidate=DB.query('SELECT id,status FROM learnings WHERE pattern_key=?',
                               (outcome['pattern'],),one=True)
            if candidate and candidate['status']=='suggested':
                graph_runtime().prepare_learning_review(candidate['id'])
        flash('Checkpointed doctor sign-off resumed and Learner re-analyzed the synthetic report.')
    except (ValueError,PermissionError,RuntimeError):
        app.logger.exception('Unable to resume graph job %s',job_id)
        flash('Unable to resume the checkpoint. Review local application logs.')
    return redirect(url_for('review_report',job_id=job_id))


@app.get('/api/v1/admin/model-configuration')
@required_role('admin')
def model_configuration():
    # Configuration metadata only: never return the AWS bearer token.
    cfg=bedrock_settings()
    return jsonify(**cfg,connection_tested=False,synthetic_only=True)


@app.get('/admin')
@required_role('admin')
def admin_dashboard():
    u=user()
    jobs=DB.query('SELECT status,COUNT(*) AS n FROM jobs GROUP BY status')
    learns=DB.query('SELECT * FROM learnings ORDER BY id DESC')
    diffs=DB.query('SELECT d.type,d.pattern_key,j.id AS job_id,j.created_at FROM job_diffs d JOIN jobs j ON j.id=d.job_id ORDER BY d.id DESC LIMIT 10')
    skill=DB.query('SELECT * FROM skills ORDER BY version DESC LIMIT 1',one=True)
    aud=DB.query('SELECT action,resource_type,created_at FROM audit_events ORDER BY id DESC LIMIT 8')
    skill_versions=DB.query('SELECT id,version,content,created_at FROM skills ORDER BY version DESC LIMIT 12')
    traces=DB.query('SELECT agent,stage,status,job_id,created_at FROM workflow_events ORDER BY id DESC LIMIT 20')
    approval_checkpoints={l['id']:graph_runtime().checkpoint_summary(f"vaidya:approval:{l['id']}")
                          for l in learns if l['status']=='suggested'}
    llm_calls=DB.query('SELECT provider,model,latency_ms,input_tokens,output_tokens,created_at '
                       'FROM llm_calls ORDER BY id DESC LIMIT 10')
    return render_template('admin.html',who=u,jobs=jobs,learnings=learns,diffs=diffs,skill=skill,
                           audit=aud,traces=traces,skill_versions=skill_versions,approval_checkpoints=approval_checkpoints,
                           bedrock_config=bedrock_settings(),llm_calls=llm_calls)


@app.post('/admin/learnings/<int:learning_id>/decision')
@required_role('admin')
def learning_decision(learning_id):
    check_csrf();u=user();decision=request.form.get('decision')
    if decision not in ('approved','rejected','deferred'):abort(400)
    learning=DB.query('SELECT * FROM learnings WHERE id=?',(learning_id,),one=True)
    if not learning or learning['status'] not in ('suggested',):abort(409,'Learning is not approvable')
    if decision=='approved' and learning['supporting_jobs']<5:abort(409,'Insufficient verified job evidence')
    try:
        graph_runtime().decide_learning(learning_id,u['id'],decision)
    except (ValueError,PermissionError,RuntimeError) as exc:
        abort(409,str(exc))
    flash('LangGraph approval checkpoint resumed. Administrator decision recorded and governed skill version applied where approved.')
    return redirect(url_for('admin_dashboard'))


@app.post('/admin/skills/rollback')
@required_role('admin')
def rollback_skill():
    """Activate an older approved skill by creating a new version, not erasing history."""
    check_csrf()
    u=user()
    try: target=int(request.form.get('target_version','0'))
    except ValueError:abort(400,'Invalid version')
    if target<1:abort(400,'Invalid version')
    with DB.connect() as c:
        prior=c.execute('SELECT version,content FROM skills WHERE version=?',(target,)).fetchone()
        current=c.execute('SELECT MAX(version) FROM skills').fetchone()[0]
        if not prior or target==current:abort(409,'Select a previous approved version')
        c.execute('INSERT INTO skills(version,content,learning_id,approved_by,created_at) '
                  'VALUES(?,?,?,?,?)',(current+1,prior['content'],None,u['id'],utcnow()))
    DB.audit(u['id'],'rollback_skill','skill',target)
    flash(f'Previous approved skill v{target} restored as new immutable version v{current+1}.')
    return redirect(url_for('admin_dashboard'))


if __name__=='__main__':
    if DEMO:
        DB.seed_demo(include_patients=not AUDIO_ONLY)
        if not AUDIO_ONLY:
            create_seed_learning(DB)
    app.run(host=os.getenv('HOST','127.0.0.1'),port=int(os.getenv('PORT','5055')),debug=False)
