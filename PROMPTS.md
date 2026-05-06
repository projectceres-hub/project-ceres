# Project Ceres — Agent Prompts
Each block below is a standalone prompt. Copy the contents of the code block and paste directly into the agent.

---

## COWORK

### C-1
```
You are working on Project Ceres, a Python GM Assistant app at https://github.com/projectceres-hub/project-ceres.

Task: Refactor `register_all_commands()` in assistant.py to eliminate all lambda closures and break the function into smaller domain-grouped sub-functions.

Context:
- `register_all_commands()` is ~396 lines (L2737–3133) and registers 60+ commands using inline lambdas like:
    register_command(config, "help", lambda args: cmd_help(args, config), "Show this help message.")
- Problems: stack traces show <lambda>, lambdas can't be tested in isolation, any parameter change touches 60+ sites.

What to do:
1. Add `from functools import partial` at the top of assistant.py.
2. Replace every lambda with functools.partial. Pattern:
    lambda args: cmd_help(args, config)
    → partial(cmd_help, config=config)
3. Split register_all_commands() into domain sub-functions, each under 80 lines:
    - _register_vault_commands(config, ...)
    - _register_note_commands(config, gpt_client, history_manager, ...)
    - _register_gpt_commands(config, gpt_client, history_manager, ...)
    - _register_pdf_commands(config, ...)
    - _register_scheduler_commands(config, scheduler, scheduler_context, ...)
    - _register_misc_commands(config, ...)
4. register_all_commands() itself should be under 30 lines — just calls to those sub-functions.
5. Do not change any command names, help text, or user-visible behavior.

Acceptance criteria:
- `python assistant.py` starts and all existing commands still work.
- No `lambda` anywhere in register_all_commands() or any _register_* function.
- register_all_commands() is under 30 lines.
```

### C-2
```
You are working on Project Ceres, a Python GM Assistant app at https://github.com/projectceres-hub/project-ceres.

Task: Add thread safety to the Config dataclass and SchedulerContext class.

Context:
- Config is defined in core/config.py as a @dataclass.
- SchedulerContext is defined in assistant.py (~L89) and has @property accessors that read config.vaults, config.current_vault, and config.ignored_vaults from a background scheduler thread.
- The main thread can mutate these dicts at any time (e.g. add_vault, switch_vault).
- Python dicts are not safe for concurrent reads during mutation.

What to do:
1. Add a RLock to Config in core/config.py:
    import threading
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

2. Wrap all dict mutations in Config methods with `with self._lock:`:
    - load_settings()
    - save_settings()
    - save_vaults()
    - register_command()

3. In SchedulerContext, return snapshots (not live references) from all @property accessors:
    @property
    def vaults(self) -> Dict[str, str]:
        with self.config._lock:
            return dict(self.config.vaults)

   Do the same for current_vault and ignored_vaults.

4. Do not add any Lock outside of Config.
5. All existing behavior must remain unchanged.

Acceptance criteria:
- No threading.Lock() or threading.RLock() defined outside Config.
- SchedulerContext properties return snapshots under the lock.
- `python assistant.py` and `python ui_main.py` both start without errors.
```

### C-3
```
You are working on Project Ceres, a Python GM Assistant app at https://github.com/projectceres-hub/project-ceres.

Task: Add TTL-based cache invalidation to ContextAwareCompleter to prevent os.walk() from running on every keypress.

Context:
- ContextAwareCompleter is defined in assistant.py (~L341–527).
- _refresh_caches() calls get_note_name_list() → list_md_files() → os.walk() on the entire vault.
- This currently runs on every completion event (every keypress triggering autocomplete).
- On a vault with 1000+ notes this causes visible keystroke lag.

What to do:
1. Add to __init__:
    self._cache_ttl: float = 10.0
    self._last_cache_refresh: float = 0.0

2. Add a helper method:
    def _cache_is_stale(self) -> bool:
        import time
        return (time.monotonic() - self._last_cache_refresh) > self._cache_ttl

3. At the end of _refresh_caches(), record the refresh time:
    self._last_cache_refresh = time.monotonic()

4. In get_completions(), replace every bare _refresh_caches() call with:
    if self._cache_is_stale():
        self._refresh_caches()

5. Add a public method:
    def invalidate_cache(self) -> None:
        self._last_cache_refresh = 0.0

6. Call invalidate_cache() from any command that modifies vault contents:
    cmd_createnote, cmd_addvault, cmd_switch — after their core operation succeeds.

Do not change what completions are offered, only when the cache refreshes.

Acceptance criteria:
- Rapid keypresses do not each trigger os.walk().
- After creating a note, it appears in completions within 10 seconds (or immediately if invalidate_cache() is wired).
- `python assistant.py` starts and autocomplete still works.
```

### C-4
```
You are working on Project Ceres, a Python GM Assistant app at https://github.com/projectceres-hub/project-ceres.

Task: Add a path-validation helper to prevent user-supplied paths from escaping their vault directory.

Context:
- Several command handlers accept user-supplied file paths (PDF paths, note names) and use them in file operations without verifying they stay inside the vault.
- A path containing ../ could escape the vault directory.
- get_path_completions() already does vault_path.exists() correctly — use that as a reference for style.

What to do:
1. Add this helper near the top of assistant.py (after imports):

    def _assert_within(base: Path, target: Path, label: str = "path") -> Path:
        """Resolve target and assert it is inside base. Raises ValueError if not."""
        resolved = target.resolve()
        base_resolved = base.resolve()
        try:
            resolved.relative_to(base_resolved)
        except ValueError:
            raise ValueError(f"Refusing to access {label} outside allowed directory: {resolved}")
        return resolved

2. Add calls to _assert_within() — wrapped in try/except ValueError that prints an error and returns — in:
    - cmd_pdf2md(): before opening pdf_path
    - cmd_pdf_convert(): before opening pdf_path
    - _fixed_out_dir(): before os.makedirs()
    - Any other location where a user-supplied path is joined to a vault path and opened

3. In core/notes.py list_md_files(), after os.walk(), filter out any file whose resolved path is not inside vault_path.resolve().

Do not change function signatures or any user-visible behavior for valid paths.

Acceptance criteria:
- Passing `../../../../etc/passwd` to pdf2md prints an error and does not open the file.
- Normal paths within the vault work unchanged.
- `python assistant.py` starts without errors.
```

---

## CURSOR (AUTO)

### S-1
```
You are working on Project Ceres, a Python GM Assistant app at https://github.com/projectceres-hub/project-ceres.

Task: Change import-fallback exception handlers from `except Exception` to `except ImportError` in assistant.py.

Location: assistant.py ~L40–49 and any similar import-fallback blocks elsewhere in the file.

Current pattern:
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

Change every `except Exception:` in import-fallback blocks to `except ImportError:`.

Scope: ONLY import-fallback try/except blocks at module level. Do NOT touch exception handling inside command handler functions — those are intentionally broad and correct.

Acceptance criteria:
- All import-fallback handlers use `except ImportError:`.
- No other exception handlers are changed.
- `python assistant.py` starts without errors.
```

### S-2
```
You are working on Project Ceres, a Python GM Assistant app at https://github.com/projectceres-hub/project-ceres.

Task: Fix the unbounded history load in cmd_history_list() in assistant.py (~L805–815).

Current code:
    all_entries = history_manager.list_history(note_path, limit=9999)
    entries = all_entries[:limit]

What to do:
1. Replace the two lines above with:
    entries = history_manager.list_history(note_path, limit=limit)

2. Find the implementation of history_manager.list_history() (likely in core/history.py or a HistoryManager class). Check whether it actually respects the `limit` parameter. If it fetches everything and slices internally, fix it there too so the limit is applied before loading from disk.

Acceptance criteria:
- cmd_history_list() passes the user-requested limit directly to list_history().
- list_history() does not load more entries from disk than the requested limit.
- Behavior for the user is unchanged.
```

### S-3
```
You are working on Project Ceres, a Python GM Assistant app at https://github.com/projectceres-hub/project-ceres.

Task: Eliminate repeated os.path.exists() calls inside the batch PDF conversion loop in assistant.py.

Location: cmd_pdfbatch() ~L1346–1376 and the _next_copy_name() helper ~L1209–1215.

Current problem:
- The loop calls os.path.exists(target) and _next_copy_name() (which itself loops with os.path.exists()) for every PDF file in the batch.

What to do:
1. Before the `for fname in pdf_files:` loop, build a set of already-existing output filenames:
    existing_outputs = set(os.listdir(out_dir)) if os.path.isdir(out_dir) else set()

2. Replace `os.path.exists(target)` inside the loop with:
    os.path.basename(target) in existing_outputs

3. After each successful conversion, add the new filename to the set:
    existing_outputs.add(final_output_filename)

4. Update _next_copy_name() to accept an optional `existing: set = None` parameter.
   When provided, use `cand in existing` instead of os.path.exists(). Fall back to os.path.exists() when existing is None (for backward compatibility).

Acceptance criteria:
- Batch converting a folder of PDFs makes only one os.listdir() call, not one os.path.exists() per file.
- Output filenames are still unique (no overwrites).
- Behavior for the user is unchanged.
```

### S-4
```
You are working on Project Ceres, a Python GM Assistant app at https://github.com/projectceres-hub/project-ceres.

Task: Add a vault disk-existence check to command handlers that are currently missing it in assistant.py.

Context:
- Several handlers check `current_vault not in config.vaults` (dict membership) but never verify the vault path exists on disk.
- If a vault directory was moved or deleted, these commands fail with hard errors instead of a clear message.
- get_path_completions() (~L257–262) already does this correctly — use it as your template.

Handlers to fix (add the check to each):
- cmd_tag_list() (~L1029)
- cmd_tag_search() (~L1067)
- cmd_tag_add() (~L1096)
- cmd_history_list() (~L805)
- Any other handler that does `vault_path = Path(config.vaults[current_vault])` without a subsequent exists() check.

Add this block immediately after the `current_vault not in config.vaults` check in each function:
    vault_path = Path(config.vaults[current_vault])
    if not vault_path.exists():
        print(f"Error: Vault path '{vault_path}' does not exist on disk. "
              f"Use 'addvault' to re-register it or check that the directory is accessible.")
        return

Do not change function signatures. Do not add the check to functions that already have it.

Acceptance criteria:
- All listed handlers print the error message and return cleanly if the vault path is missing from disk.
- Normal operation (vault exists) is unchanged.
```

### S-5
```
You are working on Project Ceres, a Python GM Assistant app at https://github.com/projectceres-hub/project-ceres.

Task: Validate that the OpenAI API key is non-empty after loading in core/config.py.

Location: Config.load_settings() ~L65–90.

Context:
- If a user sets OPENAI_API_KEY="" in their .env file or settings.json, the GPT client initializes with an empty string and fails only at the first API call with a confusing error.

What to do:
Add the following block at the end of load_settings(), after the openai_key loading logic:

    if self.openai_key is not None and self.openai_key.strip() == "":
        print("Warning: OPENAI_API_KEY is set but empty. GPT features will not work.")
        print("Hint: Set a valid key in your variables.env file or in settings.json.")
        self.openai_key = None

This normalizes an empty string to None so the rest of the app can treat None as "key not set."

Acceptance criteria:
- An empty OPENAI_API_KEY triggers the warning and sets openai_key to None.
- A valid key is unaffected.
- `python assistant.py` starts without errors.
```

---

## CODEX 5.5

### D-1
```
You are working on Project Ceres, a Python GM Assistant app at https://github.com/projectceres-hub/project-ceres.

Task: Extract the shared argument-parsing and output-conflict-resolution logic from cmd_pdf2md() and cmd_pdf_convert() into reusable helpers in assistant.py.

Location:
- cmd_pdf2md() ~L1218–1300
- cmd_pdf_convert() ~L1381–1475

Both functions share identical logic for:
1. Parsing args with shlex.split() to get pdf_path and optional --map flag
2. Loading a YAML map file with error handling
3. Checking if the output file already exists and prompting the user to replace or copy

What to do:
1. Create this helper (place it near _fixed_out_dir()):

    def _load_pdf_map(map_path: str) -> dict:
        """Load and validate a YAML mapping file. Returns {} on any error."""
        try:
            with open(map_path, "r", encoding="utf-8") as f:
                result = yaml.safe_load(f) or {}
            if not isinstance(result, dict):
                print(f"Warning: Map file '{map_path}' did not contain a mapping. Using defaults.")
                return {}
            return result
        except FileNotFoundError:
            print(f"Warning: Map file '{map_path}' not found. Using default rules.")
            return {}
        except yaml.YAMLError as e:
            print(f"Error: Failed to parse map file '{map_path}': {e}")
            return {}
        except OSError as e:
            print(f"Error: Could not read map file '{map_path}': {e}")
            return {}

2. Create this helper:

    def _resolve_pdf_output(out_dir: str, base_name: str, prompt_input) -> Optional[str]:
        """
        Check if output already exists and prompt user.
        Returns the filename to use, or None if user chose to skip.
        """
        target = os.path.join(out_dir, base_name + ".md")
        if not os.path.exists(target):
            return base_name
        print(f"Output file '{base_name}.md' already exists.")
        choice = prompt_input("(R)eplace, (C)opy as new file, or (S)kip? ").strip().lower()
        if choice == "r":
            return base_name
        elif choice == "c":
            return os.path.splitext(_next_copy_name(out_dir, base_name))[0]
        else:
            print("Skipped.")
            return None

3. Refactor both cmd_pdf2md() and cmd_pdf_convert() to call these helpers instead of duplicating the logic.

Do not change the prompts shown to the user or the final conversion call in either function.

Acceptance criteria:
- No duplicated YAML-loading or output-conflict logic remains.
- User-visible prompts and behavior are identical to before.
- `python assistant.py` works as expected.
```

### D-2
```
You are working on Project Ceres, a Python GM Assistant app at https://github.com/projectceres-hub/project-ceres.

Task: Replace magic strings with named constants in assistant.py and core/config.py.

What to do:
1. Add these constants near the top of assistant.py, after imports and before any class or function:

    DEFAULT_PDF_MAP_PATH = "maps/dnd5e.yaml"
    DEFAULT_IMPORT_SUBFOLDER = "Converted"
    ERROR_NO_VAULT = "No vault is currently set. Use 'switch' or 'addvault' to set one."
    ERROR_VAULT_NOT_FOUND = "Vault '{name}' not found. Use 'vaults' to see available vaults."

2. Search assistant.py for every occurrence of the string literal "maps/dnd5e.yaml" (should appear in ~3 places) and replace each with DEFAULT_PDF_MAP_PATH.

3. Search assistant.py for hardcoded "Converted" used as an import subfolder and replace with DEFAULT_IMPORT_SUBFOLDER.

4. Search assistant.py for inline vault-not-found error strings and replace with ERROR_VAULT_NOT_FOUND.format(name=...) where appropriate.

5. In core/config.py, the Config dataclass has `default_import_subfolder: str = "Converted"`. Leave that field in place (it's a public API), but verify it's consistent with DEFAULT_IMPORT_SUBFOLDER. If assistant.py was previously hardcoding "Converted" independently of config.default_import_subfolder, unify them to use the constant.

Do not rename any config fields, settings JSON keys, or command names.

Acceptance criteria:
- The string literal "maps/dnd5e.yaml" does not appear in assistant.py.
- All replaced strings are covered by the named constants.
- `python assistant.py` starts and behavior is unchanged.
```

### D-3
```
You are working on Project Ceres, a Python GM Assistant app at https://github.com/projectceres-hub/project-ceres.

Task: Standardize error message formatting across all print() calls in assistant.py, core/notes.py, core/vaults.py, and core/gpt.py.

Apply this convention to every print() call that communicates a result to the user:
- Errors (something failed):   "Error: <Sentence ending in period.>"
- Warnings (degraded state):   "Warning: <Sentence ending in period.>"
- Hints (how to fix):          "Hint: <Sentence ending in period.>"
- Info / success messages:     No prefix. Plain sentence, ending in period.

Rules:
- Do NOT touch core/errors.py — that module is intentionally left out of scope.
- Do NOT add or remove any print() calls — only fix the text inside existing ones.
- Do NOT change program logic of any kind.
- Go file by file: assistant.py first, then core/notes.py, core/vaults.py, core/gpt.py.

Examples of fixes:
    "Note not found."                     → "Error: Note not found."
    "error writing to vault"              → "Error: Failed to write to vault."
    "Vault 'X' not found"                 → "Error: Vault 'X' not found."
    "check your api key"                  → "Hint: Check that your API key is valid."
    "Content added to {note_name}."       → unchanged (this is a success message, correct as-is)

Acceptance criteria:
- Every error print() starts with "Error: ".
- Every warning print() starts with "Warning: ".
- Every hint print() starts with "Hint: ".
- No logic changes. `python assistant.py` behavior is identical.
```

### D-4
```
You are working on Project Ceres, a Python GM Assistant app at https://github.com/projectceres-hub/project-ceres.

Task: Remove the duplicate save_vaults implementation and consolidate to Config.save_vaults().

Context:
- core/config.py has Config.save_vaults() — a method that writes config.vaults to vaults.json with full error handling.
- core/vaults.py has a module-level save_vaults(vaults_dict) function that does the exact same thing.
- Having two implementations is a maintenance hazard — they can silently diverge.

What to do:
1. First, grep the entire repo for `save_vaults` to find every call site.
2. For each call to the module-level vaults.save_vaults(...), replace it with config.save_vaults() (adjusting how config is accessed at that call site if needed).
3. Once all call sites are migrated, delete the module-level save_vaults() function from core/vaults.py.
4. Update any imports of save_vaults from core.vaults accordingly.

If any call site does not have access to the config object, pass config through or retrieve it from the nearest available scope — do not re-introduce the standalone function.

Do not change the file format (vaults.json), any settings keys, or user-visible behavior.

Acceptance criteria:
- The module-level save_vaults() function no longer exists in core/vaults.py.
- All vaults.json writes go through Config.save_vaults().
- `python assistant.py` starts and vault saving works as before.
```
