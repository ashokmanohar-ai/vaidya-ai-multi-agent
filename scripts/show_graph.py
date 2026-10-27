"""Print the actual compiled LangGraph Mermaid source, using synthetic storage."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vaidya.database import Database
from vaidya.multi_agent import GraphRuntime
root=Path(__file__).resolve().parents[1]
rt=GraphRuntime(Database(root/'instance'/'vaidya.sqlite3'),root/'instance')
try:
    print('### Parent Orchestrator graph')
    print(rt.graph.get_graph().draw_mermaid())
    print('### Pathology Agent subgraph')
    print(rt.pathology_graph.get_graph().draw_mermaid())
    print('### Learner Agent subgraph')
    print(rt.learner_graph.get_graph().draw_mermaid())
finally:rt.close()
