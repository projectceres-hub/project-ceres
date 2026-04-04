"""
Wake word utilities for Project Ceres voice commands.

Provides centralized wake word detection and stripping functionality
for the voice command system. All wake words are defined in WAKE_WORDS
and used consistently across parsers.
"""

import re
from typing import Optional, Tuple


WAKE_WORDS: tuple[str, ...] = ("veras", "chroma")


def is_wake_word(token: str) -> bool:
    """
    Return True if the given token (case-insensitive) is one of
    the configured wake words.
    
    Args:
        token: Token to check (e.g., "Veras", "chroma", "VERAS")
        
    Returns:
        True if the token matches one of the configured wake words
        (case-insensitive), False otherwise
        
    Example:
        >>> is_wake_word("Veras")
        True
        >>> is_wake_word("chroma")
        True
        >>> is_wake_word("other")
        False
    """
    return token.lower() in WAKE_WORDS


def find_wake_word_prefix(text: str) -> Optional[str]:
    """
    Check if the given text begins with a wake word (after
    stripping leading whitespace). Returns the matched wake word
    in lowercase ("veras" or "chroma") if found, otherwise None.
    
    Args:
        text: Text to check for wake word prefix
        
    Returns:
        The matched wake word in lowercase ("veras" or "chroma")
        if found, None otherwise
        
    Note:
        - Do not strip trailing punctuation here; just detect.
        - Case-insensitive.
        - Leading whitespace is ignored for detection.
        
    Example:
        >>> find_wake_word_prefix("Veras, add bookmark")
        'veras'
        >>> find_wake_word_prefix("  chroma append note")
        'chroma'
        >>> find_wake_word_prefix("regular text")
        None
    """
    stripped = text.lstrip()
    if not stripped:
        return None
    
    lowered = stripped.lower()
    for wake_word in WAKE_WORDS:
        if lowered.startswith(wake_word):
            return wake_word
    
    return None


def strip_wake_word(text: str) -> Tuple[Optional[str], str]:
    """
    If the given text starts with a wake word (optionally followed
    by commas/colons/spaces), remove the wake word prefix and
    return a (wake_word, remainder) tuple.
    
    Args:
        text: Full command text, e.g. "Veras, add bookmark: test"
        
    Returns:
        A tuple of (wake_word, remainder_text):
        - wake_word: the matched wake word in lowercase
          ("veras" or "chroma"), or None if not found.
        - remainder_text: the original text with the wake word and
          immediate punctuation/whitespace removed. If no wake word
          is found, remainder_text is the original text unchanged.
        
    Note:
        - Handles patterns like:
            "Veras, add bookmark: test"
            "  chroma add bookmark: test"
        - Uses case-insensitive comparison.
        - Strips wake word and any immediately following
          commas, colons, and whitespace.
        
    Example:
        >>> strip_wake_word("Veras, add bookmark: test")
        ('veras', 'add bookmark: test')
        >>> strip_wake_word("  chroma append note")
        ('chroma', 'append note')
        >>> strip_wake_word("regular text")
        (None, 'regular text')
    """
    stripped = text.lstrip()
    if not stripped:
        return (None, text)
    
    lowered = stripped.lower()
    for wake_word in WAKE_WORDS:
        if lowered.startswith(wake_word):
            # Found wake word, strip it and following punctuation/whitespace
            remainder = stripped[len(wake_word):]
            # Remove commas, colons, and whitespace after wake word
            remainder = re.sub(r'^[,:\s]+', '', remainder)
            return (wake_word, remainder)
    
    # No wake word found
    return (None, text)

