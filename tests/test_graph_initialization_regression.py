"""Catch callback-registration ordering bugs without requiring live LangGraph.

This is an initialization contract test using a graph API stub, NOT an E2E
LangGraph execution test. The real graph suites must still run on Windows.
"""
from __future__ import annotations

import sys
from types import ModuleType
from vaidya.database import Database
from vaidya.multi_agent import GraphRuntime


class GraphStub:
    def __init__(self, state_schema):
        self.nodes = {}
        self.edges = []

    def add_node(self, name, callback):
        assert callable(callback) or isinstance(callback, GraphStub), (name, callback)
        self.nodes[name] = callback

    def add_edge(self, source, destination):
        self.edges.append((source, destination))

    def add_conditional_edges(self, source, router, mappings):
        assert callable(router)
        self.edges.append((source, mappings))

    def compile(self, checkpointer=None):
        return self


class SaverStub:
    def __init__(self, connection):
        self.connection = connection


def test_graph_callbacks_exist_at_registration_time(tmp_path, monkeypatch):
    modules = {name: ModuleType(name) for name in (
        'langgraph', 'langgraph.graph', 'langgraph.types',
        'langgraph.checkpoint', 'langgraph.checkpoint.sqlite'
    )}
    modules['langgraph.graph'].StateGraph = GraphStub
    modules['langgraph.graph'].START = '__start__'
    modules['langgraph.graph'].END = '__end__'
    modules['langgraph.types'].interrupt = lambda _: None
    modules['langgraph.checkpoint.sqlite'].SqliteSaver = SaverStub
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    db = Database(tmp_path / 'test.db')
    db.seed_demo()
    runtime = GraphRuntime(db, tmp_path / 'instance')
    try:
        assert {'authorize_and_route', 'pathology_agent', 'learner_agent'} <= set(runtime.graph.nodes)
        assert {'doctor_review_interrupt', 'verify_doctor_approval'} <= set(runtime.pathology_graph.nodes)
        assert {'administrator_interrupt', 'apply_administrator_decision'} <= set(runtime.learner_graph.nodes)
        assert runtime.checkpoint_path.exists()
    finally:
        runtime.close()
