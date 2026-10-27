"""Render synthetic leadership UI previews without requiring Flask. Not an API test."""
from pathlib import Path
from types import SimpleNamespace
from jinja2 import Environment, FileSystemLoader, select_autoescape
BASE=Path(__file__).resolve().parents[1]
env=Environment(loader=FileSystemLoader(str(BASE/'templates')),autoescape=select_autoescape(['html']))
env.globals.update(url_for=lambda name,**kw: '/static/'+kw['filename'] if name=='static' else '#',
    csrf_token=lambda:'preview-csrf',get_flashed_messages=lambda:[],request=SimpleNamespace(endpoint='dashboard'))
doc={'id':'synthetic-report-123','status':'draft_ready','created_at':'2026-10-17T12:00:00','patient_name':'Patient Alpha','patient_code':'DEMO-101','provider':'demo-rules','model':'rules-v1',
     'translated_transcript':'Specimen: appendix. Sections reveal acute inflammation. Please bold acute inflammation in the report.',
     'original_transcript':'Specimen: appendix. Sections reveal acute inflammation. Please bold acute inflammation in the report.',
     'draft_text':'HISTOPATHOLOGY — DRAFT / NOT VALIDATED\nDICTATED OBSERVATIONS\nSpecimen: appendix.\nSections reveal acute inflammation.',
     'report_type':'histopathology'}
doctor={'name':'Dr. Brindha','role':'doctor','hospital_id':1}
admin={'name':'Demo Administrator','role':'admin','hospital_id':1}
folder=BASE/'ui_previews';folder.mkdir(exist_ok=True)
views={
 'login':{'who':None},
 'dashboard':{'who':doctor,'jobs':[{'id':'synthetic-report-123','created_at':'2026-10-17T12:00','status':'draft_ready','provider':'demo-rules','patient':'Patient Alpha','code':'DEMO-101'},
  {'id':'synthetic-report-456','created_at':'2026-10-16T15:40','status':'approved','provider':'demo-rules','patient':'Patient Beta','code':'DEMO-102'}], 'stats':{'draft_ready':1,'approved':1}},
 'new_report':{'who':doctor,'patients':[{'id':1,'name':'Patient Alpha','code':'DEMO-101'},{'id':2,'name':'Patient Beta','code':'DEMO-102'}]},
 'review':{'who':doctor,'job':doc,'findings':[{'text':'Specimen: appendix.'},{'text':'Sections reveal acute inflammation.'}],
           'instructions':[{'instruction':'Please bold acute inflammation in the report.'}],
           'trace':[{'agent':'orchestrator','stage':'authorization_and_routing','status':'completed','created_at':'2026-10-17T12:00:00'},
                    {'agent':'pathology_agent','stage':'extract_structured_fields','status':'completed','created_at':'2026-10-17T12:00:01'}],
           'checkpoint':{'exists':True,'checkpoint_id':'demo-checkpoint','stage':'awaiting_doctor_review'},'audio_count':2},
 'admin':{'who':admin,'jobs':[{'status':'draft_ready','n':1},{'status':'approved','n':7}],
          'learnings':[{'id':1,'pattern_key':'signature_block','status':'suggested','description':'Doctor repeatedly adds a signature/sign-off block.','supporting_jobs':5},
            {'id':2,'pattern_key':'demo_signature_example','status':'example_only','description':'Example learning proposal (0 verified reports).','supporting_jobs':0}],
          'diffs':[{'pattern_key':'signature_block','type':'doctor_added','job_id':'synthetic-job-1234'}],
          'skill':{'version':2,'content':'APPROVED: Add signature block'},'skill_versions':[{'version':1,'content':'Baseline'}, {'version':2,'content':'APPROVED signature'}],
          'audit':[{'action':'approve_final','resource_type':'job','created_at':'2026-10-17T12:00:00'}],
          'traces':[{'agent':'pathology_agent','stage':'doctor_review_interrupt','status':'waiting',
                     'job_id':'synthetic-report-123','created_at':'2026-10-17T12:00:02'}],
          'bedrock_config':{'provider':'demo','model':'in.openai.gpt-5.6-terra',
                            'region':'ap-south-1','credential_configured':False,'remote_opt_in':False},
          'llm_calls':[]}}
for name,context in views.items():
    env.globals['request']=SimpleNamespace(endpoint=name)
    html=env.get_template(name+'.html').render(**context)
    (folder/(name+'.html')).write_text(html,encoding='utf8')
    assert '<html' in html.lower() and '</html>' in html.lower() and 'VAIDYA' in html
print('Rendered all',len(views),'leadership UI templates')
