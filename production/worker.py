"""Independent durable worker for AWS/container hosting, never a Flask thread."""
import argparse
import logging
import os
import time
import uuid
import threading
from .settings import Settings
from .repository import Repository
from .storage import PrivateS3
from .graph import ProductionGraph

LOG=logging.getLogger('vaidya.worker')

def process_once(repo,graph,worker_id):
    repo.sweep_expired()
    task=repo.claim(worker_id)
    if not task:return False
    stop=threading.Event()
    def heartbeat():
        while not stop.wait(40):
            if not repo.extend_lease(task['id'],worker_id):
                LOG.error('Lost worker lease %s',task['id'])
                break
    beat=threading.Thread(target=heartbeat,daemon=True)
    beat.start()
    try:
        if task['kind']=='generate':
            graph.process(task['job_id'])
        elif task['kind']=='resume':
            with repo.engine.connect() as c:
                from sqlalchemy import select
                from .tables import jobs
                j=c.execute(select(jobs).where(jobs.c.id==task['job_id'])).mappings().one()
            graph.resume(task['job_id'],j['doctor_id'])
            repo.queue_work(task['job_id'],'learning')
        elif task['kind']=='learning':
            graph.analyze(task['job_id'])
        else:raise RuntimeError('Unknown work kind')
        repo.completed(task['id'])
    except Exception as exc:
        LOG.exception('job failure kind=%s work_id=%s',task['kind'],task['id'])
        repo.failed(task['id'],type(exc).__name__)
    finally:
        stop.set();beat.join(timeout=2)
    return True

def main():
    parser=argparse.ArgumentParser(description='VAIDYA secure processing worker')
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    settings=Settings.load()
    if not settings.production or not settings.allow_clinical_inputs:
        raise RuntimeError('Worker requires separately authorized production settings')
    repo=Repository(settings.database_url)
    storage=PrivateS3(settings.s3_bucket,settings.aws_region,settings.s3_kms_key)
    graph=ProductionGraph(repo,storage,settings.database_url)
    worker_id='worker-'+uuid.uuid4().hex[:12]
    while True:
        found=process_once(repo,graph,worker_id)
        if args.once:break
        if not found:time.sleep(2)

if __name__=='__main__':main()
