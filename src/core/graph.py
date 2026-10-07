"""Build and compile the ParrotGo LangGraph state machine with 8 nodes and 3 conditional edges."""

from typing import Any, Optional
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from src.core.edges import (
    route_after_extractor,
    route_after_reducer,
    route_turn_outcome,
)
from src.core.nodes.action_policy import action_policy_node
from src.core.nodes.extractor import extractor_node
from src.core.nodes.map_service import map_service_node
from src.core.nodes.persistence import persistence_node
from src.core.nodes.qa_dispatcher import qa_dispatcher_node
from src.core.nodes.response_synthesizer import response_synthesizer_node
from src.core.nodes.session_init import session_init_node
from src.core.nodes.state_reducer import state_reducer_node
from src.core.state import ParrotGoGraphState
from src.db.sqlite_manager import get_default_db_manager


def build_parrotgo_graph(checkpointer: Optional[Any] = None, db_manager=None):
    """Construct and compile the 8-node ParrotGo conversation graph."""
    manager = db_manager or get_default_db_manager()
    builder = StateGraph(ParrotGoGraphState)

    # 1. Register 8 nodes
    builder.add_node("session_init_node", lambda state: session_init_node(state, manager))
    builder.add_node("extractor_node", extractor_node)
    builder.add_node("map_service_node", map_service_node)
    builder.add_node("state_reducer_node", state_reducer_node)
    builder.add_node("qa_dispatcher_node", qa_dispatcher_node)
    builder.add_node("action_policy_node", action_policy_node)
    builder.add_node("response_synthesizer_node", response_synthesizer_node)
    builder.add_node("persistence_node", lambda state: persistence_node(state, manager))

    # 2. Add edges
    builder.add_edge(START, "session_init_node")
    builder.add_edge("session_init_node", "extractor_node")

    # Conditional edge 1: route_after_extractor
    builder.add_conditional_edges(
        "extractor_node",
        route_after_extractor,
        {
            "map_service_node": "map_service_node",
            "state_reducer_node": "state_reducer_node",
        },
    )

    builder.add_edge("map_service_node", "state_reducer_node")

    # Conditional edge 2: route_after_reducer
    builder.add_conditional_edges(
        "state_reducer_node",
        route_after_reducer,
        {
            "qa_dispatcher_node": "qa_dispatcher_node",
            "action_policy_node": "action_policy_node",
        },
    )

    builder.add_edge("qa_dispatcher_node", "action_policy_node")
    builder.add_edge("action_policy_node", "response_synthesizer_node")
    builder.add_edge("response_synthesizer_node", "persistence_node")

    # Conditional edge 3: route_turn_outcome
    builder.add_conditional_edges(
        "persistence_node",
        route_turn_outcome,
        {
            "end_turn": END,
            "terminate_session": END,
        },
    )

    saver = checkpointer if checkpointer is not None else InMemorySaver()
    return builder.compile(checkpointer=saver)
