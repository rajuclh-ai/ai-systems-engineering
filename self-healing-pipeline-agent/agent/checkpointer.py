"""
LangGraph checkpointer setup.
SqliteSaver: persists AgentState checkpoints to checkpoints.db.
Survives server restarts — HITL pauses are durable across deploys and crashes.

checkpoints.db  — LangGraph execution state (one row per node per thread)
incidents.db    — Business incident records (written by Learning Node)
"""
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

_conn = sqlite3.connect("checkpoints.db", check_same_thread=False)
checkpointer = SqliteSaver(_conn)
