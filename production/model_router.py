"""Model-agnostic extraction contract.

Bedrock is default. Alternative OpenAI-compatible inference must be approved,
HTTPS-only, and pinned to an allowlisted host. No unapproved auto-fallback.
"""
from __future__ import annotations
import json
import os
import time
import urllib.request
import urllib.error
from urllib.parse import urlparse
from vaidya.providers import BedrockConverseProvider,Extraction,SYSTEM_INSTRUCTIONS

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise urllib.error.URLError('Inference redirect denied')

def _approved_urlopen(req,timeout):
    return urllib.request.build_opener(_NoRedirect).open(req,timeout=timeout)


class ApprovedCompatibleProvider:
    def __init__(self,endpoint=None,model=None,token=None,client=None):
        self.endpoint=endpoint or os.getenv('VAIDYA_INFERENCE_ENDPOINT','')
        self.model=model or os.getenv('VAIDYA_COMPATIBLE_MODEL','')
        self.token=token if token is not None else os.getenv('VAIDYA_INFERENCE_TOKEN','')
        self.client=client
        url=urlparse(self.endpoint)
        allowed=os.getenv('VAIDYA_APPROVED_INFERENCE_HOST','')
        if url.scheme!='https' or not url.hostname or url.hostname!=allowed or url.username or url.password or url.fragment:
            raise ValueError('Inference endpoint must use HTTPS and explicitly approved host')
        if not url.path.endswith('/v1/chat/completions'):
            raise ValueError('Expected exact /v1/chat/completions path')
        if not self.model or not self.token or not os.getenv('VAIDYA_PROVIDER_RISK_APPROVED','').lower()=='true':
            raise PermissionError('Alternative provider must be explicitly approved and authenticated')

    def extract(self,transcript,approved_skills='',*,clinical_processing_approved=False):
        if clinical_processing_approved and not (
            os.getenv('APP_ENV')=='production' and os.getenv('VAIDYA_CLINICAL_INPUTS_APPROVED')=='true'):
            raise PermissionError('Clinical processing not authorized')
        if not transcript.strip() or len(transcript)>16000:raise ValueError('Invalid transcription length')
        payload={'model':self.model,'messages':[{'role':'system','content':SYSTEM_INSTRUCTIONS+'\n'+approved_skills[:1000]},
                     {'role':'user','content':'Structured extraction from provided clinician dictation data:\n'+transcript}],
                     'temperature':0,'response_format':{'type':'json_object'}}
        req=urllib.request.Request(self.endpoint,data=json.dumps(payload).encode('utf-8'),method='POST',
            headers={'Content-Type':'application/json','Authorization':'Bearer '+self.token})
        started=time.monotonic()
        try:
            opener=self.client or _approved_urlopen
            with opener(req,timeout=65) as resp:
                response=json.loads(resp.read(150_000))
        except (urllib.error.URLError,ValueError,KeyError) as err:
            raise RuntimeError('Approved inference endpoint unavailable or returned invalid JSON') from None
        choices=response.get('choices',[])
        if not choices:raise ValueError('Model returned no completion')
        content=choices[0].get('message',{}).get('content','')
        try:raw=json.loads(content)
        except (ValueError,TypeError):raise ValueError('Model output is not valid JSON') from None
        findings,instructions,flags=BedrockConverseProvider._validate_result(raw)
        usage=response.get('usage',{})
        return Extraction(findings,instructions,flags+['Doctor verification mandatory'],
             'approved-openai-compatible',self.model,usage={'inputTokens':usage.get('prompt_tokens',0),
             'outputTokens':usage.get('completion_tokens',0)},latency_ms=int((time.monotonic()-started)*1000))


def get_clinical_extractor():
    provider=os.getenv('LLM_PROVIDER','bedrock').lower()
    if provider=='bedrock':return BedrockConverseProvider()
    if provider=='openai-compatible':return ApprovedCompatibleProvider()
    raise ValueError('Only reviewed model providers are available to clinical workflows')
