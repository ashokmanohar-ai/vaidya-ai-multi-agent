"""Run explicitly with a disposable PostgreSQL database and full LangGraph deps.

Does not make AWS calls. This is a checkpoint smoke test only, not a clinical evaluation.
"""
import os
import pytest

@pytest.mark.integration
def test_pg_checkpoint_restart():
    url=os.getenv('VAIDYA_TEST_POSTGRES_URL')
    if not url:pytest.skip('Set VAIDYA_TEST_POSTGRES_URL to a disposable PostgreSQL database')
    pytest.importorskip('langgraph.checkpoint.postgres')
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.graph import StateGraph,START,END
    from typing import TypedDict
    import uuid
    class State(TypedDict,total=False): counter:int
    def double(state):return {'counter':state['counter']*2}
    builder=StateGraph(State);builder.add_node('double',double)
    builder.add_edge(START,'double');builder.add_edge('double',END)
    thread='test:'+uuid.uuid4().hex
    with PostgresSaver.from_conn_string(url) as saver:
        saver.setup()
        g=builder.compile(checkpointer=saver)
        assert g.invoke({'counter':2},{'configurable':{'thread_id':thread}})['counter']==4
    with PostgresSaver.from_conn_string(url) as saver:
        g=builder.compile(checkpointer=saver)
        snap=g.get_state({'configurable':{'thread_id':thread}})
        assert snap.values['counter']==4
