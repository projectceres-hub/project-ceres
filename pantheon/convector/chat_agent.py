"""
pantheon/convector/chat_agent.py — Project Ceres
=================================================
Natural-language dispatcher for the GM Assistant chat interface.

Uses GPT-4o to interpret user intent, answer vault questions, and
dispatch to registered Pantheon commands.  Maintains a short
conversation history so follow-up messages feel continuous.

Response contract (always JSON):
    {
        "reply":  str,                                 # shown in chat
        "action": null | {"command": str, "args": str} # optional dispatch
    }

Usage::

    from pantheon.convector.chat_agent import ChatAgent, ChatResponse

    agent = ChatAgent(config)
    response = agent.process("Play some tense battle music")
    # response.reply   → "On it! Searching Spotify for battle music…"
    # response.command → "spotify-play"
    # response.args    → "tense battle music"
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional


# ── Response dataclass ────────────────────────────────────────────────────────

@dataclass
class ChatResponse:
    """Structured response from the chat agent."""

    reply: str
    """Friendly reply text to display in the chat bubble."""

    command: Optional[str] = None
    """Pantheon command name to dispatch (e.g. 'spotify-play'), or None."""

    args: Optional[str] = None
    """Arguments string for the command, or None."""

    action_label: Optional[str] = None
    """Human-readable description of the action being taken."""

    error: Optional[str] = None
    """Set if the agent call itself failed (not a command error)."""


# ── ChatAgent ─────────────────────────────────────────────────────────────────

class ChatAgent:
    """
    Natural-language GM assistant powered by GPT-4o.

    Converts free-text messages into friendly replies and optional
    Pantheon command dispatches.  Keeps a rolling conversation window
    so follow-ups ("what about the second note?") stay coherent.

    Args:
        config: Fully-initialised Config dataclass.  Provides the
                OpenAI API key and the active vault name.
    """

    _MODEL         = "gpt-4o"
    _HISTORY_LIMIT = 14       # messages kept in sliding window (7 turns)
    _MAX_TOKENS    = 512

    # ── System prompt ─────────────────────────────────────────────────────────
    _SYSTEM = """\
You are Ceres — the Game Master assistant for Project Ceres, a modular \
TTRPG session tool.  You help GMs run their sessions through natural language. \
Be warm, brief, and practical.  You are a capable companion, not a search engine.

== AVAILABLE COMMANDS ==
Dispatch a command by setting the "action" field in your JSON response.

VAULT & NOTES
  search <query>            Search notes in the active vault
  read <filename>           Read a specific note by name
  list [folder]             List markdown files in the vault
  tree                      Show the vault folder structure
  tag-list                  List all tags in the vault

CAMPAIGNS & SESSIONS
  session-create            Create a new session note (will prompt in console)
  campaign-create <name>    Create a new campaign folder structure
  fgu-import-log            Import a Fantasy Grounds chat log

SPOTIFY  (requires Spotify panel connected)
  spotify-play <query>      Search for and play music
  spotify-pause             Pause playback
  spotify-skip              Skip to the next track
  spotify-stop              Stop playback

DISCORD  (requires Discord panel connected)
  discord-start-recording   Start recording the active voice channel
  discord-stop-recording    Stop recording and trigger transcription

SCHEDULER
  schedule-start            Start background automation jobs
  schedule-stop             Stop background jobs
  snapshot-run-now          Take an immediate vault snapshot

INDEXING
  index                     Rebuild the vault search index
  srd-index                 Rebuild the SRD index

== RESPONSE FORMAT ==
ALWAYS respond with valid JSON only — no markdown, no extra text:

  { "reply": "<1-3 sentence friendly response>", "action": null }

OR if an action should be taken:

  { "reply": "<1-3 sentence response>",
    "action": { "command": "<command-name>", "args": "<args or empty>" } }

== GUIDELINES ==
- If the user asks about their notes/campaign, emit a search action and tell \
them you're looking it up — the search result will be injected as context \
so you can answer in your next response.
- If a request is ambiguous, ask ONE short clarifying question.
- Prefer action over explanation — take the action and say what you did.
- Never refuse a reasonable GM request.
- Keep replies short.  One or two sentences is usually enough.
"""

    def __init__(self, config) -> None:
        self._config  = config
        self._client  = None          # lazy-initialised OpenAI client
        self._history: List[Dict[str, str]] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def process(self, user_message: str, extra_context: str = "") -> ChatResponse:
        """
        Process a natural-language message and return a ChatResponse.

        Args:
            user_message:  Raw text from the chat input field.
            extra_context: Optional extra context to inject (e.g. search
                           results from a previous action turn).

        Returns:
            ChatResponse with reply text and an optional command to dispatch.
        """
        try:
            client = self._get_client()
        except Exception as exc:
            return ChatResponse(
                reply=(
                    "I can't reach the AI service right now. "
                    "Check your OPENAI_API_KEY in variables.env and try again."
                ),
                error=str(exc),
            )

        messages = [{"role": "system", "content": self._build_system(extra_context)}]
        messages.extend(self._history[-self._HISTORY_LIMIT:])
        messages.append({"role": "user", "content": user_message})

        try:
            resp = client.chat.completions.create(
                model=self._MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.72,
                max_tokens=self._MAX_TOKENS,
            )
            raw = resp.choices[0].message.content
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = self._extract_json(raw)
        except Exception as exc:
            return ChatResponse(
                reply="Something went wrong reaching the AI. Try again in a moment.",
                error=str(exc),
            )

        reply   = str(data.get("reply", "I'm not sure how to help with that."))
        action  = data.get("action")
        command = args = action_label = None

        if isinstance(action, dict):
            command = str(action.get("command", "")).strip()
            args    = str(action.get("args", "")).strip()
            if command:
                action_label = f"{command} {args}".strip()
            else:
                command = None

        # Update conversation history
        self._history.append({"role": "user",      "content": user_message})
        self._history.append({"role": "assistant",  "content": raw})

        return ChatResponse(
            reply=reply,
            command=command,
            args=args or None,
            action_label=action_label,
        )

    def inject_result(self, command: str, result: str) -> None:
        """
        Feed a command result back into the conversation history so the
        agent can reference it in the next response turn.

        Args:
            command: The command that was run.
            result:  Its output string (truncated to 2000 chars if long).
        """
        if result and result.strip():
            snippet = result.strip()[:2000]
            self._history.append({
                "role":    "user",
                "content": f"[System: '{command}' returned:]\n{snippet}",
            })

    def clear_history(self) -> None:
        """Reset the conversation to a clean slate."""
        self._history.clear()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_client(self):
        """Lazy-initialise the OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI  # noqa: PLC0415
            except ImportError as exc:
                raise RuntimeError(
                    "openai package not installed. Run: pip install openai"
                ) from exc
            # Config stores the key as `openai_key` (loaded from OPENAI_API_KEY in variables.env)
            api_key = getattr(self._config, "openai_key", None)
            if not api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY not set. Add it to variables.env and restart the app."
                )
            self._client = OpenAI(api_key=api_key)
        return self._client

    # ── Setup instructions shown to the user when an integration is missing ─────
    _SETUP_HINTS = {
        "spotify": (
            "Spotify is not set up yet.  To enable it, go to "
            "https://developer.spotify.com/dashboard, create an app, and add "
            "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to variables.env, then restart."
        ),
        "discord": (
            "Discord is not set up yet.  To enable it, go to "
            "https://discord.com/developers/applications, create a bot, copy its token, "
            "and add DISCORD_BOT_TOKEN to variables.env, then restart."
        ),
    }

    def _build_system(self, extra_context: str) -> str:
        """Build the system prompt, injecting current context and integration status."""
        vault = getattr(self._config, "current_vault", None) or "no vault selected"
        ctx   = f"\n\n== CURRENT CONTEXT ==\nActive vault: {vault}"

        # ── Integration status ────────────────────────────────────────────────
        status_lines: list[str] = []

        spotify_ok = bool(
            os.environ.get("SPOTIFY_CLIENT_ID", "").strip() and
            os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
        )
        discord_ok = bool(os.environ.get("DISCORD_BOT_TOKEN", "").strip())

        if spotify_ok:
            status_lines.append("Spotify: CONNECTED — spotify-* commands are available.")
        else:
            status_lines.append(
                "Spotify: NOT CONFIGURED — do NOT dispatch spotify-* commands. "
                "If the user asks about Spotify or music, tell them it is not set up yet "
                "and share this setup hint: " + self._SETUP_HINTS["spotify"]
            )

        if discord_ok:
            status_lines.append("Discord: CONNECTED — discord-* commands are available.")
        else:
            status_lines.append(
                "Discord: NOT CONFIGURED — do NOT dispatch discord-* commands. "
                "If the user asks about Discord or recording, tell them it is not set up yet "
                "and share this setup hint: " + self._SETUP_HINTS["discord"]
            )

        ctx += "\n\n== INTEGRATION STATUS ==\n" + "\n".join(status_lines)

        if extra_context:
            ctx += f"\n\nAdditional context from previous action:\n{extra_context}"
        return self._SYSTEM + ctx

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Best-effort JSON extraction when the model forgets the format."""
        if not text:
            return {}
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except (json.JSONDecodeError, ValueError):
                pass
        return {"reply": text.strip()}
