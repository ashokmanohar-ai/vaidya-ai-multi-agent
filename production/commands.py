"""One-time operator runbooks, no default credentials."""
import argparse
from .settings import Settings
from .repository import Repository

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('init-db')
    sub.add_parser('init-checkpoints')
    admin=sub.add_parser('bootstrap-admin')
    for key in ('hospital','email','name'):admin.add_argument('--'+key,required=True)
    admin.add_argument('--password-stdin',action='store_true',required=True)
    new_user=sub.add_parser('create-user')
    for key in ('admin-id','hospital-id','email','name','role'):
        new_user.add_argument('--'+key,required=True)
    new_user.add_argument('--password-stdin',action='store_true',required=True)
    args=p.parse_args()
    settings=Settings.load()
    repo=Repository(settings.database_url)
    if args.action=='init-db':
        from alembic.config import Config
        from alembic import command
        cfg=Config('deployment/alembic.ini')
        cfg.set_main_option('sqlalchemy.url',settings.database_url)
        command.upgrade(cfg,'head')
        print('Database migrations complete')
    elif args.action=='init-checkpoints':
        from langgraph.checkpoint.postgres import PostgresSaver
        with PostgresSaver.from_conn_string(settings.database_url.replace('postgresql+psycopg://','postgresql://')) as saver:
            saver.setup()
        print('LangGraph checkpoint tables initialized')
    elif args.action=='create-user':
        import sys
        pwd=sys.stdin.readline().rstrip('\r\n')
        uid=repo.add_user(args.admin_id,args.hospital_id,args.name,args.email,pwd,args.role)
        print('Provisioned user id',uid)
    elif args.action=='bootstrap-admin':
        import sys
        pwd=sys.stdin.readline().rstrip('\r\n')
        result=repo.bootstrap(args.hospital,args.email,args.name,pwd)
        print('Bootstrap completed for administrator id',result['administrator_id'])

if __name__=='__main__':main()
