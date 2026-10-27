"""Model-agnostic extraction workflow; optional real LangGraph StateGraph execution.

Demo note: audio ASR and Tamil-English translation are not implemented; the
clinician explicitly supplies a synthetic transcript. A translation placeholder
passes it through unchanged and is labeled as such, never as a translated result.
"""
import os
from .providers import get_provider
from .reports import report_text


def run_extraction(transcript):
    provider=get_provider()
    extraction=provider.extract(transcript)
    return {
       'findings':extraction.findings,'instructions':extraction.instructions,
       'review_flags':extraction.review_flags,
       'draft_text':report_text(extraction.findings,extraction.instructions,extraction.review_flags),
       'provider':extraction.provider,'model':extraction.model
    }


def build_graph():
    """LangGraph path available when requirements-graph.txt dependencies are installed."""
    from typing import TypedDict
    from langgraph.graph import StateGraph, START, END
    class PathologyState(TypedDict, total=False):
        transcript:str
        validated_transcript:str
        structured:dict
        status:str
        review_required:bool

    def validate_intake(state:PathologyState):
        transcript=state.get('transcript','').strip()
        if not transcript: raise ValueError('Synthetic transcript required')
        return {'validated_transcript':transcript,'status':'transcript_provided_no_asr'}

    def extract_fields(state:PathologyState):
        return {'structured':run_extraction(state['validated_transcript']),'status':'extraction_ready'}

    def validate_output(state:PathologyState):
        structured=state['structured']
        if not isinstance(structured.get('findings'),list):raise ValueError('Missing findings list')
        return {'review_required':True,'status':'awaiting_doctor_review'}

    graph=StateGraph(PathologyState)
    graph.add_node('validate_input',validate_intake)
    graph.add_node('extract_structured_fields',extract_fields)
    graph.add_node('validate_output',validate_output)
    graph.add_edge(START,'validate_input')
    graph.add_edge('validate_input','extract_structured_fields')
    graph.add_edge('extract_structured_fields','validate_output')
    graph.add_edge('validate_output',END)
    return graph.compile()


def run_pipeline(transcript):
    if os.environ.get('USE_LANGGRAPH','').lower() not in ('true','1'):
        return run_extraction(transcript)
    graph=build_graph()
    result=graph.invoke({'transcript':transcript})
    assert result['status']=='awaiting_doctor_review'
    return result['structured']
