"""Portable SQLAlchemy schema; UUID strings are opaque identifiers."""
from sqlalchemy import (MetaData, Table, Column, String, Integer, Text, DateTime,
                        ForeignKey, UniqueConstraint, Boolean, Index)
from sqlalchemy.sql import func, true

metadata = MetaData()
hospitals = Table('clinical_hospitals', metadata,
    Column('id',String(36),primary_key=True), Column('name',String(180),nullable=False),
    Column('active',Boolean,nullable=False,server_default=true()))
users = Table('clinical_users',metadata,
    Column('id',String(36),primary_key=True),Column('hospital_id',String(36),ForeignKey('clinical_hospitals.id'),nullable=False),
    Column('email',String(255),nullable=False,unique=True),Column('name',String(150),nullable=False),
    Column('password_hash',Text,nullable=False),Column('role',String(24),nullable=False),
    Column('failed_attempts',Integer,nullable=False,server_default='0'),Column('locked_until',DateTime(timezone=True)),
    Column('is_active',Boolean,nullable=False,server_default=true()))
patients = Table('clinical_patients',metadata,
    Column('id',String(36),primary_key=True),Column('hospital_id',String(36),ForeignKey('clinical_hospitals.id'),nullable=False),
    Column('reference',String(80),nullable=False),Column('display_name',String(160),nullable=False),
    UniqueConstraint('hospital_id','reference'))
jobs = Table('clinical_jobs',metadata,
    Column('id',String(36),primary_key=True),Column('hospital_id',String(36),ForeignKey('clinical_hospitals.id'),nullable=False),
    Column('doctor_id',String(36),ForeignKey('clinical_users.id'),nullable=False),
    Column('patient_id',String(36),ForeignKey('clinical_patients.id'),nullable=False),
    Column('report_type',String(64),nullable=False),Column('language_config',String(10),nullable=False,server_default='en'),Column('status',String(32),nullable=False),
    Column('input_key',String(400),nullable=False),Column('draft_key',String(400)),Column('draft_sha256',String(64)),
    Column('final_key',String(400)),Column('final_sha256',String(64)),
    Column('approved_by',String(36),ForeignKey('clinical_users.id')),Column('skill_version',Integer,nullable=False,server_default='1'),
    Column('model_id',String(160)),Column('error_code',String(80)),
    Column('approved_at',DateTime(timezone=True)),Column('created_at',DateTime(timezone=True),server_default=func.now(),nullable=False),
    Column('updated_at',DateTime(timezone=True),server_default=func.now(),nullable=False),
    Column('idempotency_key',String(100),nullable=False),
    UniqueConstraint('doctor_id','idempotency_key'))
assets = Table('clinical_assets',metadata,
    Column('id',String(36),primary_key=True),Column('job_id',String(36),ForeignKey('clinical_jobs.id'),nullable=False),
    Column('hospital_id',String(36),ForeignKey('clinical_hospitals.id'),nullable=False),
    Column('object_key',String(400),nullable=False,unique=True),Column('sequence',Integer,nullable=False,server_default='0'),Column('kind',String(16),nullable=False),
    Column('content_type',String(100),nullable=False),Column('size_bytes',Integer,nullable=False),
    Column('uploaded',Boolean,nullable=False,server_default='false'))
work = Table('clinical_work',metadata,
    Column('id',String(36),primary_key=True),Column('job_id',String(36),ForeignKey('clinical_jobs.id'),nullable=False),
    Column('kind',String(24),nullable=False),Column('status',String(20),nullable=False),
    Column('attempts',Integer,nullable=False,server_default='0'),Column('lease_until',DateTime(timezone=True)),
    Column('worker_id',String(100)),Column('next_run_at',DateTime(timezone=True),server_default=func.now()),
    Column('last_error',String(80)),UniqueConstraint('job_id','kind'))
audit = Table('clinical_audit',metadata,
    Column('id',String(36),primary_key=True),Column('actor_id',String(36)),Column('hospital_id',String(36)),
    Column('action',String(90),nullable=False),Column('resource_type',String(40),nullable=False),
    Column('resource_id',String(100),nullable=False),Column('at',DateTime(timezone=True),server_default=func.now(),nullable=False),
    Column('detail_code',String(80)))
learnings = Table('clinical_learnings',metadata,
    Column('id',String(36),primary_key=True),Column('hospital_id',String(36),ForeignKey('clinical_hospitals.id'),nullable=False),
    Column('specialty',String(50),nullable=False),Column('pattern',String(90),nullable=False),
    Column('support',Integer,nullable=False),Column('description',Text,nullable=False),
    Column('status',String(24),nullable=False),Column('reviewed_by',String(36)),
    Column('reviewed_at',DateTime(timezone=True)),UniqueConstraint('hospital_id','specialty','pattern'))
skills = Table('clinical_skills',metadata,
    Column('id',String(36),primary_key=True),Column('hospital_id',String(36),ForeignKey('clinical_hospitals.id'),nullable=False),
    Column('specialty',String(50),nullable=False),Column('version',Integer,nullable=False),
    Column('content',Text,nullable=False),Column('reviewed_by',String(36),nullable=False),
    Column('created_at',DateTime(timezone=True),server_default=func.now()),
    UniqueConstraint('hospital_id','specialty','version'))
Index('idx_clinical_work_claim',work.c.status,work.c.next_run_at)
Index('idx_clinical_jobs_scope',jobs.c.hospital_id,jobs.c.doctor_id)

ai_events = Table('clinical_ai_events',metadata,
    Column('id',String(36),primary_key=True),
    Column('job_id',String(36),ForeignKey('clinical_jobs.id'),nullable=False),
    Column('stage',String(30),nullable=False),Column('provider',String(40),nullable=False),
    Column('model',String(160),nullable=False),Column('latency_ms',Integer,nullable=False),
    Column('input_tokens',Integer),Column('output_tokens',Integer))
