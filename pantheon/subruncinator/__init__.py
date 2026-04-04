"""
Subruncinator domain for Project Ceres.

This domain handles cleanup and maintenance - removing temporary files, cleaning
caches, and maintaining vault health by pruning unwanted or outdated information.

Public API exports from the cleanup modules.
"""

from .cleanup import (
    find_temp_files,
    find_temp_directories,
    delete_files,
    delete_empty_directories,
    clean_cache,
)

__all__ = [
    "find_temp_files",
    "find_temp_directories",
    "delete_files",
    "delete_empty_directories",
    "clean_cache",
]

