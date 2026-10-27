"""SQLite repository and synthetic demo setup. No real patient data permitted in demo."""
import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 230000).hex()
    return f'pbkdf2_sha256$230000${salt}${digest}'


def verify_password(password, stored):
    try:
        algo, iters, salt, val = stored.split('$')
        if algo != 'pbkdf2_sha256': return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iters)).hex()
        return hmac.compare_digest(digest, val)
    except (ValueError, TypeError):
        return False


class Database:
    def __init__(self, path):
        self.path = str(path)

    @contextmanager
    def connect(self):
        Path(self.path).parent.mkdir(parents=True,exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=20000')
        conn.execute('PRAGMA journal_mode=WAL')
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def query(self, sql, params=(), one=False):
        with self.connect() as c:
            rows = c.execute(sql, params).fetchall()
            rows = [dict(row) for row in rows]
            return (rows[0] if rows else None) if one else rows

    def execute(self, sql, params=()):
        with self.connect() as c:
            cur = c.execute(sql, params)
            return cur.lastrowid

    def init(self):
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS hospitals (
              id INTEGER PRIMARY KEY, name TEXT NOT NULL, logo_text TEXT NOT NULL, address TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
              role TEXT NOT NULL CHECK(role IN ('doctor','admin')),
              hospital_id INTEGER REFERENCES hospitals(id), password_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS patients (
              id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
              age INTEGER, sex TEXT, hospital_id INTEGER NOT NULL REFERENCES hospitals(id));
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id),
              doctor_id INTEGER NOT NULL REFERENCES users(id), hospital_id INTEGER NOT NULL REFERENCES hospitals(id),
              report_type TEXT NOT NULL, original_transcript TEXT NOT NULL,
              translated_transcript TEXT NOT NULL, findings_json TEXT NOT NULL,
              instruction_json TEXT NOT NULL, draft_text TEXT NOT NULL, final_text TEXT,
              draft_filename TEXT NOT NULL, image_json TEXT NOT NULL DEFAULT '[]',
              provider TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,
              created_at TEXT NOT NULL, approved_at TEXT, approved_by INTEGER REFERENCES users(id),
              error_message TEXT);
            CREATE INDEX IF NOT EXISTS idx_jobs_doctor ON jobs(doctor_id,created_at);
            CREATE TABLE IF NOT EXISTS job_inputs (
              id INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
              seq INTEGER NOT NULL, kind TEXT NOT NULL,
              private_ref TEXT, metadata_json TEXT NOT NULL DEFAULT '{}',
              UNIQUE(job_id,seq,kind));
            CREATE TABLE IF NOT EXISTS job_diffs (
              id INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
              type TEXT NOT NULL, before_text TEXT NOT NULL, after_text TEXT NOT NULL,
              pattern_key TEXT NOT NULL, reviewed INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS learnings (
              id INTEGER PRIMARY KEY, pattern_key TEXT NOT NULL UNIQUE,
              description TEXT NOT NULL, supporting_jobs INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL DEFAULT 'suggested', created_at TEXT NOT NULL,
              decided_at TEXT, decided_by INTEGER REFERENCES users(id));
            CREATE TABLE IF NOT EXISTS skills (
              id INTEGER PRIMARY KEY, version INTEGER NOT NULL UNIQUE,
              content TEXT NOT NULL, learning_id INTEGER REFERENCES learnings(id),
              approved_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS workflow_events (
              id INTEGER PRIMARY KEY, workflow_id TEXT NOT NULL, job_id TEXT NOT NULL,
              agent TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL,
              created_at TEXT NOT NULL, UNIQUE(workflow_id,stage));
            CREATE INDEX IF NOT EXISTS idx_workflow_events_job ON workflow_events(job_id,id);
            CREATE TABLE IF NOT EXISTS audit_events (
              id INTEGER PRIMARY KEY, actor_id INTEGER, action TEXT NOT NULL,
              resource_type TEXT NOT NULL, resource_id TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS llm_calls (
              id INTEGER PRIMARY KEY, workflow_id TEXT NOT NULL, job_id TEXT NOT NULL,
              provider TEXT NOT NULL, model TEXT NOT NULL, latency_ms INTEGER NOT NULL DEFAULT 0,
              input_tokens INTEGER, output_tokens INTEGER, total_tokens INTEGER,
              created_at TEXT NOT NULL, UNIQUE(workflow_id,job_id));
            CREATE INDEX IF NOT EXISTS idx_llm_calls_job ON llm_calls(job_id);
            ''')
            cols={r[1] for r in c.execute('PRAGMA table_info(jobs)').fetchall()}
            if 'skills_version' not in cols:
                c.execute('ALTER TABLE jobs ADD COLUMN skills_version INTEGER NOT NULL DEFAULT 1')
            if 'validation_json' not in cols:
                c.execute("ALTER TABLE jobs ADD COLUMN validation_json TEXT NOT NULL DEFAULT '{}'")
            if 'review_json' not in cols:
                c.execute("ALTER TABLE jobs ADD COLUMN review_json TEXT NOT NULL DEFAULT '{}'")


    def audit(self, actor, action, resource, key):
        self.execute('INSERT INTO audit_events(actor_id,action,resource_type,resource_id,created_at) VALUES(?,?,?,?,?)',
                     (actor, action, resource, str(key), utcnow()))

    def seed_demo(self, doctor_password='DemoDoctor!2026', admin_password='DemoAdmin!2026', *, include_patients=True):
        self.init()
        with self.connect() as c:
            if c.execute('SELECT count(*) FROM hospitals').fetchone()[0]: return
            c.execute('INSERT INTO hospitals(name,logo_text,address) VALUES(?,?,?)',
                      ('Brindha Pathology & Diagnostics','BRINDHA PATHOLOGY','Chennai, Tamil Nadu · DEMONSTRATION ONLY'))
            c.execute('INSERT INTO users(email,name,role,hospital_id,password_hash) VALUES(?,?,?,?,?)',
                      ('doctor@vaidya.demo','Dr. Brindha','doctor',1,password_hash(doctor_password)))
            c.execute('INSERT INTO users(email,name,role,hospital_id,password_hash) VALUES(?,?,?,?,?)',
                      ('admin@vaidya.demo','Demo Administrator','admin',1,password_hash(admin_password)))
            cases=[('DEMO-101','Patient Alpha',45,'Female'),('DEMO-102','Patient Beta',52,'Male'),
                   ('DEMO-103','Patient Gamma',36,'Female'),('DEMO-104','Patient Delta',28,'Male'),
                   ('DEMO-105','Patient Epsilon',63,'Female'),('DEMO-106','Patient Zeta',40,'Male'),
                   ('DEMO-107','Patient Eta',58,'Female')]
            if include_patients:
                c.executemany('INSERT INTO patients(code,name,age,sex,hospital_id) VALUES(?,?,?,?,1)',cases)
            c.execute('INSERT INTO skills(version,content,learning_id,approved_by,created_at) VALUES(1,?,?,?,?)',
                      ('Baseline: report only dictated findings; flag ambiguity; require doctor approval.',None,2,utcnow()))
