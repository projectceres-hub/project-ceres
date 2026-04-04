"""
Occator domain for Project Ceres.

This domain handles search and SRD index refinement - building and querying
indices for vault content and System Reference Documents.

Public API exports from the search and SRD indexing modules.
"""

from .search_index import (
    build_search_index,
    save_index,
    load_index,
    search_index,
    cmd_search,
)
from .srd_index import (
    build_srd_index,
    search_srd_index,
    cmd_srd_index,
    cmd_search_srd,
)

__all__ = [
    # Search index functions
    "build_search_index",
    "save_index",
    "load_index",
    "search_index",
    "cmd_search",
    # SRD index functions
    "build_srd_index",
    "search_srd_index",
    "cmd_srd_index",
    "cmd_search_srd",
]
