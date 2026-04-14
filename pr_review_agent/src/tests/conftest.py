"""Add src/ to sys.path so tests can import project modules directly."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
