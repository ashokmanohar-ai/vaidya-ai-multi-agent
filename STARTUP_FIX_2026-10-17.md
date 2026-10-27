# VAIDYA AI startup fix — callback registration order

## Reported failure

`GraphRuntime.__init__` raised `UnboundLocalError` on startup at:

`pathology.add_node('doctor_review_interrupt', await_doctor)`

## Root cause

The local function `await_doctor()` (and `verify_doctor_approval()`) were defined **below** the code that attempted to register them in the LangGraph `StateGraph`. Python had not yet executed their definitions when node registration took place.

## Correction

Moved those two function definitions above `pathology=StateGraph(VaidyaState)` and its `add_node(...)` registrations. The graph topology, state schema, and callbacks remain otherwise unchanged.

## Verification

41 existing/added domain and regression checks passed on the packaging host, including a graph-construction test that would have caught the original ordering error. The host cannot install Flask/LangGraph from the package registry, so full LangGraph checkpoint/resume execution is **not verified** here. Run `python scripts\validate_complete.py` on the target Windows environment. Do not assume validation is complete until it exits with code 0 and zero skipped integration tests.

## Safe use

Use synthetic data only. No real patient information. For AWS Bedrock, keep the bearer token in local `.env` or the host secrets store; do not put it into Git or share it.
