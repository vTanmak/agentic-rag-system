"""
backend/api/__init__.py

Aggregates all route routers into one place for clean import in main.py.
"""

from backend.api import chat, collections, documents, eval

__all__ = ["collections", "documents", "chat", "eval"]
