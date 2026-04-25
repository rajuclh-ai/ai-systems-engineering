"""
LangGraph checkpointer setup.
MemorySaver: in-memory, sufficient for dev and testing.
Enables: graph pause (HITL), resume after approval, crash recovery.
"""
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
