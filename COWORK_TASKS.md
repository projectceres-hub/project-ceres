# Project Ceres — Code Review Task Briefing
**For:** Cowork (orchestrator)  
**Delegates:** Codex 5.5 (routine / mechanical edits) · Cursor auto (surgical per-function fixes)  
**Source review:** Full repo at https://github.com/projectceres-hub/project-ceres  
**Language:** Python · Main file: `assistant.py` (3,269 lines)

---

## Project context

Project Ceres is a GM Assistant desktop app for tabletop RPGs. It manages Obsidian markdown vaults, converts PDFs, integrates with OpenAI GPT, and schedules sessions. It has two entry points: `assistant.py` (CLI REPL) and `ui_main.py` (PyQt5/PySide6 GUI). The two share a `Config` dataclass defined in `core/config.py`. Commands are registered via `register_all_commands()` in `assistant.py` and dispatched by `run_command()`.

Key modules:
- `assistant.py` — monolithic main file, CLI entry point, all command handlers
- `core/config.py` — `Config` dataclass, settings load/save
- `core/gpt.py` — `GPTClient` wrapper and GPT-based note commands
- `core/notes.py` — note listing, reading, creation
- `core/vaults.py` — vault management
- `core/errors.py` — global error handler, logging

All command handlers follow this pattern:
```python
def cmd_something(args, vaults, current_vault, prompt_input, ...) -> None
```
They are registered as lambdas inside `register_all_commands()` which binds the config parameters. The goal of every task below is to make the code easier to understand, safer, and more maintainable — **without changing any user-visible behavior**.

---

## Division of labor

| Agent | Role | Assigned tasks |
|-------|------|----------------|
| **Cowork** | Orchestrates, handles architectural changes | C-1, C-2, C-3, C-4 |
| **Codex 5.5** | Mechanical, repetitive, low-risk edits | D-1, D-2, D-3, D-4 |
| **Cursor auto** | Surgical per-function correctness/perf fixes | S-1, S-2, S-3, S-4, S-5 |

Work can proceed in parallel within each tier. Cowork tasks should be reviewed before merges since they touch the most code.

---

---

# COWORK TASKS

---

## C-1 — Refactor `register_all_commands()` from lambdas to `functools.partial`

**File:** `assistant.py`  
**Lines:** ~2737–3133  
**Priority:** Critical — this is the highest-leverage change in the repo.

### Context
`register_all_commands()` is 396 lines long and registers 60+ commands, every single one using an inline lambda to bind config parameters:
```python
register_command(
    config,
    "help",
    lambda args: cmd_help(args, config),
    "Show this help message."
)
```
Problems: stack traces show `<lambda>`, lambdas can't be tested in isolation, parameter changes require editing 60+ sites.

### What to do
1. Replace every lambda with `functools.partial`. The pattern is:
   ```python
   from functools import partial
   register_command(config, "help", partial(cmd_help, config=config), "Show this help message.")
   ```
   For commands that take `args` as first positional param, use:
   ```python
   partial(cmd_help, config=config)
   # equivalent to: lambda args: cmd_help(args, config=config)
   ```
2. After replacing all lambdas, split `register_all_commands()` into sub-functions grouped by domain — each called from `register_all_commands()`:
   - `_register_vault_commands(config, ...)` — vault, switch, addvault, ignorevault, etc.
   - `_register_note_commands(config, ...)` — list, read, createnote, tree, search, tags, etc.
   - `_register_gpt_commands(config, gpt_client, ...)` — gptwrite, editnote, send, etc.
   - `_register_pdf_commands(config, ...)` — pdf2md, pdfbatch, pdf-convert, pdf-batch, etc.
   - `_register_scheduler_commands(config, scheduler, ...)` — schedule, sessions, etc.
   - `_register_misc_commands(config, ...)` — help, exit, history, etc.
3. Each sub-function should be under 80 lines.
4. Do not change any command names, help text, or behavior.

### Acceptance criteria
- `python assistant.py` starts and all existing commands still work
- No `lambda` in `register_all_commands()` or any `_register_*` function
- `register_all_commands()` itself is under 30 lines (just calls to the sub-functions)

---

## C-2 — Add thread safety to `Config` and `SchedulerContext`

**Files:** `core/config.py`, `assistant.py` (`SchedulerContext` class ~L89)  
**Priority:** High — the background scheduler thread reads and the main thread writes shared vault state.

### Context
`SchedulerContext` uses a live `@property` to read `config.vaults` from a background thread while the main thread can mutate it (e.g., `add_vault`, `switch_vault`). Python dicts are not safe for concurrent reads during mutation.

### What to do
1. Add a `threading.RLock` to `Config`:
   ```python
   import threading
   
   @dataclass
   class Config:
       ...
       _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)
   ```
2. Wrap all dict mutations (`vaults`, `ignored_vaults`, `commands`) with `with self._lock:` in `Config` methods (`save_vaults`, `save_settings`, `register_command`, `load_settings`).
3. In `SchedulerContext`, acquire the lock when reading `config.vaults`:
   ```python
   @property
   def vaults(self) -> Dict[str, str]:
       with self.config._lock:
           return dict(self.config.vaults)  # return a snapshot, not a live reference
   ```
4. Do the same for `current_vault` and `ignored_vaults` properties.
5. All existing tests (if any) and `python assistant.py` must still work.

### Acceptance criteria
- No `threading.Lock()` defined outside `Config`
- All access to `config.vaults` from `SchedulerContext` goes through the lock
- The scheduler background thread cannot see a partially-mutated vault dict

---

## C-3 — Add time-based cache invalidation to `ContextAwareCompleter`

**File:** `assistant.py`  
**Lines:** `ContextAwareCompleter` class ~L341–527, `_refresh_caches()` ~L374  
**Priority:** Medium — causes keystroke lag on large vaults.

### Context
`_refresh_caches()` calls `get_note_name_list()` which calls `list_md_files()` which calls `os.walk()` on the entire vault. This runs on every completion event (every keypress triggering autocomplete). On a vault with 1,000+ notes this causes visible lag.

### What to do
1. Add two timestamp attributes to `ContextAwareCompleter.__init__`:
   ```python
   self._cache_ttl: float = 10.0  # seconds before cache expires
   self._last_cache_refresh: float = 0.0
   ```
2. Replace the unconditional `_refresh_caches()` calls in `get_completions()` with a TTL check:
   ```python
   import time

   def _cache_is_stale(self) -> bool:
       return (time.monotonic() - self._last_cache_refresh) > self._cache_ttl

   def _refresh_caches(self) -> None:
       """Refresh cached note and tag lists."""
       self._note_cache = get_note_name_list(self.config, self.error_func)
       self._tag_cache = get_tag_completions(self.config)
       self._last_cache_refresh = time.monotonic()
   ```
3. In `get_completions()`, replace every bare `_refresh_caches()` call with:
   ```python
   if self._cache_is_stale():
       self._refresh_caches()
   ```
4. Also add a `invalidate_cache()` method that resets `_last_cache_refresh = 0.0`, and call it from any command that modifies vault contents (e.g., `cmd_createnote`, `cmd_addvault`, `cmd_switch`) so the cache goes stale immediately after a mutation rather than waiting for the TTL.

### Acceptance criteria
- Typing rapidly in the REPL does not trigger repeated `os.walk()` calls on every keypress
- After creating a new note, it appears in completions within `cache_ttl` seconds (or immediately if `invalidate_cache()` is wired up)
- No change to what completions are offered — only when the cache refreshes

---

## C-4 — Validate file paths are inside their vault (path traversal prevention)

**File:** `assistant.py`, `core/notes.py`  
**Lines:** Multiple — `cmd_pdf2md` ~L1231, `_fixed_out_dir` ~L1191, `list_md_files` in `notes.py`  
**Priority:** High

### Context
User-supplied paths are used in file operations. While `list_md_files()` limits results to vault contents, there are several places where a user-supplied path (e.g., a PDF path or a note name containing `../`) could escape the intended directory.

### What to do
1. Add a helper function near the top of `assistant.py`:
   ```python
   def _assert_within(base: Path, target: Path, label: str = "path") -> Path:
       """
       Resolve `target` and assert it is inside `base`.
       Raises ValueError if not.
       """
       resolved = target.resolve()
       base_resolved = base.resolve()
       try:
           resolved.relative_to(base_resolved)
       except ValueError:
           raise ValueError(f"Refusing to access {label} outside of vault: {resolved}")
       return resolved
   ```
2. Call `_assert_within(vault_path, Path(user_supplied_path))` in:
   - `cmd_pdf2md()` before opening `pdf_path`
   - `cmd_pdf_convert()` before opening `pdf_path`
   - `_fixed_out_dir()` before `os.makedirs()`
   - Any place a user-supplied path is joined to a vault path and opened
3. Wrap each call in a `try/except ValueError` that prints a clear error and returns early — do not raise to the user.
4. In `notes.py` `list_md_files()`, add a filter to exclude any result where `Path(full_path).resolve()` is not inside `vault_path.resolve()`.

### Acceptance criteria
- A path like `../../../../etc/passwd` passed to `pdf2md` prints an error and does not open the file
- Normal paths within the vault continue to work unchanged

---

---

# CURSOR (AUTO) TASKS

---

## S-1 — Fix overly broad `except Exception` on import fallbacks

**File:** `assistant.py`  
**Lines:** ~40–49  
**Priority:** High

### What to do
Change all import fallback handlers from `except Exception:` to `except ImportError:`.

Current:
```python
try:
    from prompt_toolkit.completion import CompleteStyle
except Exception:
    try:
        from prompt_toolkit.shortcuts.prompt import CompleteStyle
    except Exception:
        try:
            from prompt_toolkit.enums import CompleteStyle
        except Exception:
            CompleteStyle = None
```

Change every `except Exception:` in this block (and any similar import-fallback blocks in the file) to `except ImportError:`. This ensures that actual programming errors (e.g., `AttributeError` inside the module) are not silently swallowed.

**Scope:** Only import-fallback `try/except` blocks. Do not touch the error handling in command handlers — those are intentionally broad and are correct.

---

## S-2 — Fix unbounded history load in `cmd_history_list()`

**File:** `assistant.py`  
**Lines:** ~L805–815  
**Priority:** High

### What to do
The current code:
```python
all_entries = history_manager.list_history(note_path, limit=9999)
entries = all_entries[:limit]
```
Should become:
```python
entries = history_manager.list_history(note_path, limit=limit)
```
Pass the user-requested `limit` directly to `list_history()` instead of fetching 9999 and slicing. Verify that `history_manager.list_history()` actually respects the `limit` parameter (check its implementation). If it does not, fix it there too.

---

## S-3 — Pre-collect existing filenames before batch PDF loop

**File:** `assistant.py`  
**Lines:** `cmd_pdfbatch()` ~L1346–1376  
**Priority:** High

### What to do
The current loop calls `os.path.exists()` and `_next_copy_name()` (which itself loops with `os.path.exists()`) for every file in the batch.

Before the `for fname in pdf_files:` loop, build a set of existing output filenames once:
```python
existing_outputs = set(os.listdir(out_dir)) if os.path.isdir(out_dir) else set()
```
Then replace `os.path.exists(target)` with `os.path.basename(target) in existing_outputs`, and update `existing_outputs.add(...)` after each successful conversion so subsequent iterations see the newly-created files.

Also update `_next_copy_name()` to accept an optional `existing: set` parameter and use that instead of repeated `os.path.exists()` calls when provided.

---

## S-4 — Add vault disk-existence check to command handlers that are missing it

**File:** `assistant.py`  
**Priority:** High

### What to do
Several command handlers check `current_vault not in config.vaults` (dict membership) but do not verify the vault path actually exists on disk. Add a disk check immediately after the dict check in each of these functions:

- `cmd_tag_list()` (~L1029)
- `cmd_tag_search()` (~L1067)  
- `cmd_tag_add()` (~L1096)
- `cmd_history_list()` (~L805)
- Any other command that does `vault_path = Path(config.vaults[current_vault])` without checking `vault_path.exists()`

The pattern to add after the dict membership check:
```python
vault_path = Path(config.vaults[current_vault])
if not vault_path.exists():
    print(f"Error: Vault path '{vault_path}' does not exist on disk. "
          f"Use 'addvault' to re-register it or check that the directory is accessible.")
    return
```

Do not change function signatures. Do not add the check to functions that already have it (e.g., `get_path_completions` already does this correctly — use that as the template).

---

## S-5 — Validate OpenAI key is non-empty after loading

**File:** `core/config.py`  
**Lines:** `load_settings()` ~L65–90  
**Priority:** Medium

### What to do
After the block that loads `openai_key` from `settings.json` and the `.env` file, add:
```python
if self.openai_key is not None and self.openai_key.strip() == "":
    print("Warning: OPENAI_API_KEY is set but empty. GPT features will not work.")
    print("Hint: Set a valid key in your variables.env file or settings.json.")
    self.openai_key = None  # treat empty string same as not set
```
This prevents the GPT client from initializing with an empty key and failing only at the first API call with a confusing error.

---

---

# CODEX 5.5 TASKS

---

## D-1 — Extract shared PDF conversion logic into a helper function

**File:** `assistant.py`  
**Lines:** `cmd_pdf2md()` ~L1218–1300, `cmd_pdf_convert()` ~L1381–1475  
**Priority:** Medium

### What to do
Both `cmd_pdf2md()` and `cmd_pdf_convert()` follow the exact same pattern:
1. `shlex.split(args)` to get `pdf_path` and optional `--map` flag
2. Load `map_path` YAML with identical error handling
3. Check if output file exists → prompt replace/copy
4. Call the actual conversion function

Extract steps 2–3 into a shared helper:
```python
def _load_pdf_map(map_path: str) -> dict:
    """Load and validate a YAML mapping file for PDF conversion.
    Returns empty dict on any error (already printed to user)."""
    ...

def _resolve_pdf_output(out_dir: str, base_name: str, prompt_input) -> Optional[str]:
    """Check if output already exists, prompt user, return final filename or None to skip."""
    ...
```
Then refactor both commands to call these helpers. The actual conversion call at the end stays different between the two commands — that's fine, don't try to merge that part.

Make sure: no behavior change, same prompts shown to user, same error messages.

---

## D-2 — Replace magic strings with named constants

**File:** `assistant.py` (and `core/config.py` where relevant)  
**Priority:** Medium

### What to do
Define these constants near the top of `assistant.py` (after imports, before any class/function):
```python
DEFAULT_PDF_MAP_PATH = "maps/dnd5e.yaml"
DEFAULT_IMPORT_SUBFOLDER = "Converted"
ERROR_NO_VAULT = "No vault is currently set. Use 'switch' or 'addvault' to set one."
ERROR_VAULT_NOT_FOUND = "Vault '{name}' not found. Use 'vaults' to see available vaults."
```
Then do a find-and-replace for each literal occurrence in `assistant.py`. Also remove the `default_import_subfolder: str = "Converted"` default from `Config` and import `DEFAULT_IMPORT_SUBFOLDER` from `assistant.py`, or define it in a shared `constants.py` module.

Search for: `"maps/dnd5e.yaml"` — should appear in 3 places.  
Search for: inline repetitions of vault-not-found error strings.

Do not rename any public API, config fields, or settings JSON keys.

---

## D-3 — Standardize error message formatting across command handlers

**File:** `assistant.py`, `core/notes.py`, `core/vaults.py`, `core/gpt.py`  
**Priority:** Medium

### What to do
Currently some errors print `Error: ...`, some print plain sentences, some end with periods, some don't. The goal is consistency, not changing the `core/errors.py` logging system (leave that alone).

Apply this standard to all `print()` calls that communicate errors to the user:
- **Errors** (something failed): `Error: <sentence ending in period.>`
- **Warnings** (degraded behavior): `Warning: <sentence ending in period.>`
- **Hints** (how to fix): `Hint: <sentence ending in period.>` — keep these where they exist, add them where they're clearly missing
- **Info / success** messages: No prefix, just the message.

Go file by file. Change the phrasing of the `print()` text only — do not change program logic, do not add/remove print calls, do not touch `core/errors.py`.

---

## D-4 — Remove duplicate `save_vaults` implementation

**File:** `core/vaults.py` (module-level function) vs `core/config.py` (`Config.save_vaults()` method)  
**Priority:** Medium

### What to do
Both `vaults.save_vaults(vaults_dict)` (module-level in `core/vaults.py`) and `config.save_vaults()` (method on `Config`) write to `vaults.json` with identical logic. Having two is a maintenance hazard — they can drift.

1. Keep `Config.save_vaults()` as the canonical implementation (it already has proper error handling).
2. Change the module-level `save_vaults()` in `core/vaults.py` to a thin delegation shim, or remove it entirely if nothing outside of `Config` calls the module-level version directly.
3. Search the codebase for all calls to the module-level `vaults.save_vaults(...)` and reroute them to `config.save_vaults()`.
4. Update all imports accordingly.

Do not change the file format or any existing behavior. Run a grep for `save_vaults` across the repo to find all call sites before touching anything.

---

## Notes for all agents

- **Do not change user-facing behavior** — command names, prompts shown to user, file formats, and settings JSON keys must remain identical.
- **Run `python assistant.py` and `python ui_main.py`** to verify nothing is broken after each task.
- **One PR per task** is preferred. If two tasks touch the same function, coordinate before both editing it.
- The `core/errors.py` logging infrastructure is intentionally left out of scope — it's already well-designed.
- There are no automated tests in this repo yet. Be conservative: prefer minimal diffs over clever rewrites.
