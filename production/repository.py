"""Hospital-scoped data access and transactionally claimed durable work.

Only the service layer knows IDs; LLMs never receive database tools.
"""
from __future__ import annotations
import uuid
from datetime import datetime,timedelta,timezone
from sqlalchemy import create_engine,select,insert,update,func,or_
from sqlalchemy.exc import IntegrityError
from .tables import metadata,hospitals,users,patients,jobs,assets,work,audit,learnings,skills
from .passwords import create_hash,verify_hash


def now(): return datetime.now(timezone.utc)
def ident(): return str(uuid.uuid4())

class Repository:
    def __init__(self,url: str):
        self.engine=create_engine(url,pool_pre_ping=True,future=True)
        self.postgres=self.engine.dialect.name=='postgresql'
    def migrate_for_test(self):
        if self.postgres:raise RuntimeError('Production schema changes must use Alembic')
        metadata.create_all(self.engine)
    def audit(self,actor,hospital,action,resource_type,resource_id,code=None):
        with self.engine.begin() as c:
            c.execute(insert(audit).values(id=ident(),actor_id=actor,hospital_id=hospital,
                      action=action,resource_type=resource_type,resource_id=str(resource_id),detail_code=code))
    def find_user(self,email):
        with self.engine.connect() as c:
            return c.execute(select(users).where(users.c.email==email.lower())).mappings().first()
    def account(self,uid):
        with self.engine.connect() as c:
            return c.execute(select(users).where(users.c.id==uid,users.c.is_active==True)).mappings().first()
    def authenticate(self,email,password):
        with self.engine.begin() as c:
            user=c.execute(select(users).where(users.c.email==email.strip().lower()).with_for_update()).mappings().first()
            if not user or not user['is_active']:return None
            locked=user['locked_until']
            if locked is not None:
                if locked.tzinfo is None:locked=locked.replace(tzinfo=timezone.utc)
                if locked>now():return None
            if not verify_hash(password,user['password_hash']):
                failures=user['failed_attempts']+1
                c.execute(update(users).where(users.c.id==user['id']).values(failed_attempts=failures,
                   locked_until=(now()+timedelta(minutes=15)) if failures>=5 else None))
                return None
            c.execute(update(users).where(users.c.id==user['id']).values(failed_attempts=0,locked_until=None))
            return dict(user)
    def bootstrap(self,hospital_name,email,name,password):
        """Explicit one-time bootstrap invoked from CLI, never on process start."""
        if not all(x.strip() for x in (hospital_name,email,name)):raise ValueError('Missing bootstrap values')
        with self.engine.begin() as c:
            if c.execute(select(func.count()).select_from(users)).scalar():
                raise RuntimeError('Bootstrap disabled: users already exist')
            hid=ident();uid=ident()
            c.execute(insert(hospitals).values(id=hid,name=hospital_name))
            c.execute(insert(users).values(id=uid,hospital_id=hid,email=email.strip().lower(),name=name,
                          role='admin',password_hash=create_hash(password)))
            c.execute(insert(skills).values(id=ident(),hospital_id=hid,specialty='pathology',version=1,
              content='Only clinician-dictated findings; ambiguous content must be flagged; doctor approval mandatory',reviewed_by=uid))
            return {'hospital_id':hid,'administrator_id':uid}
    def add_user(self,admin,hospital,name,email,password,role):
        if role not in ('doctor','admin'):raise ValueError('Invalid role')
        a=self.account(admin)
        if not a or a['role']!='admin' or a['hospital_id']!=hospital:raise PermissionError('Admin access required')
        new=ident()
        with self.engine.begin() as c:
            c.execute(insert(users).values(id=new,hospital_id=hospital,email=email.lower(),name=name,role=role,
                         password_hash=create_hash(password)))
        self.audit(admin,hospital,'create_user','user',new)
        return new
    def add_patient(self,actor,hospital,reference,display_name):
        self.authorize_actor(actor,hospital,'doctor')
        if not (1<=len(reference)<=80 and 1<=len(display_name)<=160):raise ValueError('Invalid patient fields')
        pid=ident()
        with self.engine.begin() as c:
            c.execute(insert(patients).values(id=pid,hospital_id=hospital,reference=reference,
                          display_name=display_name))
        self.audit(actor,hospital,'create_patient','patient',pid)
        return pid
    def authorize_actor(self,actor,hospital,role=None):
        user=self.account(actor)
        if not user or user['hospital_id']!=hospital or (role and user['role']!=role):
            raise PermissionError('Access denied')
        return user
    def authorized_patient(self,actor,hospital,patient):
        self.authorize_actor(actor,hospital,'doctor')
        with self.engine.connect() as c:
            p=c.execute(select(patients).where(patients.c.id==patient,patients.c.hospital_id==hospital)).mappings().first()
        if not p:raise PermissionError('Patient outside permitted hospital')
        return p
    def patient_list(self,actor,hospital):
        self.authorize_actor(actor,hospital,'doctor')
        with self.engine.connect() as c:
            return [dict(x) for x in c.execute(select(patients.c.id,patients.c.reference,patients.c.display_name)
                        .where(patients.c.hospital_id==hospital)).mappings()]
    def create_job(self,actor,hospital,patient,input_key,idempotency_key,job_id=None,language_config="en",expect_uploads=False):
        self.authorized_patient(actor,hospital,patient)
        if language_config not in ('en','ta','ta-en'):raise ValueError('Unsupported language configuration')
        if not 12<=len(idempotency_key)<=100:raise ValueError('Missing or weak idempotency key')
        key=job_id or ident()
        try:
            with self.engine.begin() as c:
                existing=c.execute(select(jobs.c.id).where(jobs.c.doctor_id==actor,
                            jobs.c.idempotency_key==idempotency_key)).scalar_one_or_none()
                if existing:return existing,False
                version=c.execute(select(func.max(skills.c.version)).where(skills.c.hospital_id==hospital,
                            skills.c.specialty=='pathology')).scalar() or 1
                c.execute(insert(jobs).values(id=key,hospital_id=hospital,doctor_id=actor,patient_id=patient,
                    report_type='histopathology',language_config=language_config,status='awaiting_uploads' if expect_uploads else 'queued',input_key=input_key,
                    skill_version=version,idempotency_key=idempotency_key))
                c.execute(insert(work).values(id=ident(),job_id=key,kind='generate',status='held' if expect_uploads else 'queued',attempts=0,
                    next_run_at=now()))
        except IntegrityError:
            # A concurrent request may have won the idempotency race.
            prior=self.get_idempotent_job(actor,idempotency_key)
            if not prior:raise
            return prior,False
        self.audit(actor,hospital,'create_job','job',key)
        return key,True
    def get_job(self,actor,job_id,doctor_only=True):
        user=self.account(actor)
        if not user:raise PermissionError('Authentication required')
        stmt=select(jobs).where(jobs.c.id==job_id,jobs.c.hospital_id==user['hospital_id'])
        if doctor_only or user['role']=='doctor':stmt=stmt.where(jobs.c.doctor_id==actor)
        with self.engine.connect() as c: j=c.execute(stmt).mappings().first()
        if not j:raise PermissionError('Job is not accessible')
        return dict(j)
    def get_idempotent_job(self,actor,idempotency_key):
        with self.engine.connect() as c:
            return c.execute(select(jobs.c.id).where(jobs.c.doctor_id==actor,
                jobs.c.idempotency_key==idempotency_key)).scalar_one_or_none()
    def asset_create(self,actor,job_id,object_key,kind,mime):
        job=self.get_job(actor,job_id)
        if job['status'] not in ('queued','awaiting_uploads'):raise ValueError('Uploads closed')
        if kind not in ('audio','image'):raise ValueError('Invalid asset kind')
        allowed={'audio':('audio/wav','audio/mpeg','audio/mp4','audio/webm','audio/ogg'),
                 'image':('image/png','image/jpeg')}
        if mime not in allowed[kind]:raise ValueError('Invalid MIME')
        with self.engine.begin() as c:
            count=c.execute(select(func.count()).select_from(assets).where(
                assets.c.job_id==job_id,assets.c.kind==kind)).scalar()
            if count>=5:raise ValueError('Maximum five files of this type')
            aid=ident()
            c.execute(insert(assets).values(id=aid,job_id=job_id,hospital_id=job['hospital_id'],
                 object_key=object_key,sequence=count+1,kind=kind,content_type=mime,size_bytes=0,uploaded=False))
        return aid
    def asset_confirm(self,actor,job_id,asset_id,size):
        job=self.get_job(actor,job_id)
        if job['status'] not in ('queued','awaiting_uploads'):raise ValueError('Job no longer accepts uploads')
        with self.engine.begin() as c:
            row=c.execute(select(assets).where(assets.c.id==asset_id,
                assets.c.job_id==job_id,assets.c.hospital_id==job['hospital_id'])).mappings().first()
            if not row:raise PermissionError('Asset outside job scope')
            c.execute(update(assets).where(assets.c.id==asset_id).values(uploaded=True,size_bytes=size))
        return dict(row)
    def asset_list(self,actor,job_id):
        job=self.get_job(actor,job_id)
        with self.engine.connect() as c:
            return [dict(r) for r in c.execute(select(assets).where(assets.c.job_id==job_id,
                    assets.c.hospital_id==job['hospital_id'])).mappings()]
    def submit_confirmed_uploads(self,actor,job_id):
        job=self.get_job(actor,job_id)
        if job['status']!='awaiting_uploads':raise ValueError('Job is not waiting for files')
        with self.engine.begin() as c:
            pending=c.execute(select(func.count()).select_from(assets).where(
                assets.c.job_id==job_id,assets.c.uploaded==False)).scalar()
            complete=c.execute(select(func.count()).select_from(assets).where(
                assets.c.job_id==job_id,assets.c.uploaded==True)).scalar()
            audio_complete=c.execute(select(func.count()).select_from(assets).where(
                assets.c.job_id==job_id,assets.c.kind=='audio',assets.c.uploaded==True)).scalar()
            if pending or not complete or not audio_complete:
                raise ValueError('At least one confirmed uploaded audio file is required')
            c.execute(update(jobs).where(jobs.c.id==job_id,jobs.c.status=='awaiting_uploads').values(
                     status='queued',updated_at=now()))
            c.execute(update(work).where(work.c.job_id==job_id,work.c.kind=='generate',work.c.status=='held')
                      .values(status='queued'))
        self.audit(actor,job['hospital_id'],'finalize_uploads','job',job_id)
    def extend_lease(self,task_id,worker_id,lease_seconds=180):
        with self.engine.begin() as c:
            result=c.execute(update(work).where(work.c.id==task_id,work.c.worker_id==worker_id,
                    work.c.status=='leased').values(lease_until=now()+timedelta(seconds=lease_seconds)))
            return result.rowcount==1
    def queue_work(self,job_id,kind):
        if kind not in ('generate','learning','resume'):raise ValueError('Unknown job kind')
        with self.engine.begin() as c:
            exists=c.execute(select(work.c.id).where(work.c.job_id==job_id,work.c.kind==kind)).scalar_one_or_none()
            if exists:return exists
            wid=ident()
            c.execute(insert(work).values(id=wid,job_id=job_id,kind=kind,status='queued',attempts=0,next_run_at=now()))
            return wid
    def claim(self,worker_id,max_attempts=3,lease_seconds=180):
        """PG SELECT FOR UPDATE SKIP LOCKED and bounded at-least-once processing."""
        right_now=now()
        with self.engine.begin() as c:
            stmt=select(work).where(work.c.attempts<max_attempts,
                      or_(work.c.status=='queued',
                          (work.c.status=='leased') & (work.c.lease_until<right_now)),
                      work.c.next_run_at<=right_now).order_by(work.c.next_run_at)
            if self.postgres:stmt=stmt.with_for_update(skip_locked=True)
            task=c.execute(stmt.limit(1)).mappings().first()
            if not task:return None
            result=c.execute(update(work).where(work.c.id==task['id'],
                           work.c.attempts==task['attempts'],
                           work.c.status==task['status']).values(status='leased',attempts=task['attempts']+1,
                           worker_id=worker_id,lease_until=right_now+timedelta(seconds=lease_seconds)))
            if result.rowcount!=1:return None
            return {**dict(task),'attempts':task['attempts']+1}
    def sweep_expired(self,max_attempts=3):
        """Mark unrecoverable abandoned leases failed for operator visibility."""
        expired=[]
        with self.engine.begin() as c:
            rows=c.execute(select(work).where(work.c.status=='leased',work.c.attempts>=max_attempts,
                         work.c.lease_until<now()).with_for_update(skip_locked=self.postgres)).mappings().all()
            for task in rows:
                c.execute(update(work).where(work.c.id==task['id'],work.c.status=='leased').values(
                    status='failed',last_error='WORKER_LEASE_EXHAUSTED',lease_until=None))
                if task['kind']=='generate':
                    c.execute(update(jobs).where(jobs.c.id==task['job_id'],jobs.c.status=='queued').values(
                              status='failed',error_code='WORKER_LEASE_EXHAUSTED'))
                expired.append(task['id'])
        return expired
    def completed(self,task_id):
        with self.engine.begin() as c:
            c.execute(update(work).where(work.c.id==task_id,work.c.status=='leased')
                      .values(status='done',lease_until=None))
    def failed(self,task_id,error_code,max_attempts=3):
        with self.engine.begin() as c:
            task=c.execute(select(work).where(work.c.id==task_id).with_for_update()).mappings().first()
            if not task:return
            exhausted=task['attempts']>=max_attempts
            c.execute(update(work).where(work.c.id==task_id).values(
                status='failed' if exhausted else 'queued',last_error=error_code[:80],lease_until=None,
                next_run_at=now()+timedelta(seconds=min(120,2**task['attempts']))))
            if exhausted and task['kind']=='generate':
                c.execute(update(jobs).where(jobs.c.id==task['job_id'],jobs.c.status=='queued')
                          .values(status='failed',error_code=error_code[:80],updated_at=now()))
    def set_draft(self,job_id,key,model_id,checksum=None):
        with self.engine.begin() as c:
            result=c.execute(update(jobs).where(jobs.c.id==job_id,jobs.c.status=='queued')
                     .values(status='draft_ready',draft_key=key,draft_sha256=checksum,model_id=model_id,updated_at=now()))
            if result.rowcount!=1:
                current=c.execute(select(jobs.c.status,jobs.c.draft_key).where(jobs.c.id==job_id)).first()
                if not current or current[0]!='draft_ready' or current[1]!=key:
                    raise RuntimeError('Illegal draft transition')
    def approve(self,actor,job_id,final_key,checksum=None):
        job=self.get_job(actor,job_id)
        self.authorize_actor(actor,job['hospital_id'],'doctor')
        with self.engine.begin() as c:
            result=c.execute(update(jobs).where(jobs.c.id==job_id,jobs.c.status=='draft_ready',jobs.c.doctor_id==actor)
                             .values(status='approved',approved_at=now(),approved_by=actor,final_key=final_key,final_sha256=checksum,updated_at=now()))
            if result.rowcount!=1:raise ValueError('Already finalized or not ready for review')
        self.queue_work(job_id,'resume')
        self.audit(actor,job['hospital_id'],'approve_report','job',job_id)
    def approve_learning(self,actor,learning_id,decision):
        if decision not in ('approved','rejected','deferred'):raise ValueError('Invalid decision')
        admin=self.account(actor)
        if not admin or admin['role']!='admin':raise PermissionError('Admin required')
        with self.engine.begin() as c:
            item=c.execute(select(learnings).where(learnings.c.id==learning_id,
               learnings.c.hospital_id==admin['hospital_id']).with_for_update()).mappings().first()
            if not item or item['status']!='suggested':raise ValueError('Suggestion not pending')
            if decision=='approved' and item['support']<5:raise ValueError('Insufficient independent evidence')
            c.execute(update(learnings).where(learnings.c.id==learning_id).values(status=decision,reviewed_by=actor,reviewed_at=now()))
            if decision=='approved':
                version=c.execute(select(func.max(skills.c.version)).where(skills.c.hospital_id==admin['hospital_id'],
                          skills.c.specialty==item['specialty'])).scalar() or 0
                current=c.execute(select(skills.c.content).where(skills.c.hospital_id==admin['hospital_id'],
                          skills.c.specialty==item['specialty'],skills.c.version==version)).scalar_one_or_none() or ''
                c.execute(insert(skills).values(id=ident(),hospital_id=admin['hospital_id'],specialty=item['specialty'],
                           version=version+1,content=current+'\nAPPROVED: '+item['description'],reviewed_by=actor))
        self.audit(actor,admin['hospital_id'],'learning_'+decision,'learning',learning_id)
    def learning_candidates(self,actor):
        user=self.account(actor)
        if not user or user['role']!='admin':raise PermissionError('Admin required')
        with self.engine.connect() as c:
            return [dict(v) for v in c.execute(select(learnings).where(learnings.c.hospital_id==user['hospital_id'])).mappings()]
