"""Offline synthetic structured-report smoke test; no ASR/API calls or PHI."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from docx import Document
from vaidya.structured_review import FIELDS, validate_fields, formatted_report
from vaidya.clinical_review import assess_report, final_document_issues
from vaidya.reports import structured_final_docx

ROOT=Path(__file__).resolve().parents[1]
PATIENT={'code':'DEMO-2026','name':'Example Patient','age':25,'sex':'Female'}
AUDIO_SIMULATED_TEXT='Patient name Mrs. Example Patient age 25 female. Specimen appendix. Gross: appendix 5 cm. Microscopy: no atypical cells seen. Impression: acute appendicitis.'
FIELDS_VERIFIED={
 'specimen':'Appendix', 'referring_doctors':'Dr. Example Referrer / Dr. Synthetic Colleague',
 'biopsy_id':'DEMO/2007/2026','received_date':'01/06/2026','reported_date':'04/06/2026',
 'gross':'Appendix measuring 5 cm, cut surface shows a patent lumen and normal tip.',
 'microscopy':'Sections show inflamed appendicular mucosa with neutrophils and lymphocytes. No atypical cells seen.',
 'impression':'Features of acute appendicitis.',
}

def main():
    a=assess_report(PATIENT,AUDIO_SIMULATED_TEXT,[{'text':AUDIO_SIMULATED_TEXT}],[],audio_present=True)
    fields_form={**FIELDS_VERIFIED,'attest':'yes',**{'confirmed_'+key:'yes' for key,_,_ in FIELDS},
       **{key:'yes' for key in ('verified_audio','verified_identity','verified_numbers','verified_negations','verified_instructions')}}
    verified,errors=validate_fields(fields_form,assessment=a,patient=PATIENT)
    if errors:raise RuntimeError('Unexpected synthetic review validation error: '+str(errors))
    if final_document_issues(formatted_report(PATIENT,verified),a):raise RuntimeError('Synthetic final failed the source safety gate')
    output=ROOT/'demo_outputs'/'VAIDYA_Synthetic_Structured_Verified_Example.docx'
    structured_final_docx(verified,{'id':'synthetic-smoke-2026'},PATIENT,
       {'logo_text':'SYNTHETIC PATHOLOGY','address':'LOCAL DEMONSTRATION ONLY'},output)
    doc=Document(output)
    assert 'No atypical cells seen.' in '\n'.join(p.text for p in doc.paragraphs)
    print('PASS: structured validation, date/identifier, negation, patient reconciliation, DOCX creation')
    print('Synthetic-only demonstration file:',output)

if __name__=='__main__':main()
