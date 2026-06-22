# Infinite Table Mode Architecture Note

## Intent

Project Ceres should support two synchronized views over one shared session workspace:

| Mode | Role |
|---|---|
| Command Center | Fast live-session action through dockable/floating panels |
| Infinite Table | Spatial prep, relationship mapping, scene staging, and session overview |

The Infinite Table must not become a separate data system. Notes, NPCs, locations, encounters, audio sources, reminders, timelines, and SRD references should be workspace objects that can render as docked panels, compact chips, full viewers, canvas cards, or pinned widgets.

## Current Repo Fit

The seed already exists in `pantheon/vervactor/workspace.py`:

- `WorkspaceState` tracks active vault, campaign, session, scene, layout profile, and current object.
- `WorkspaceObjectRef` gives panels a common way to describe the focused object.
- `load_scene_data` / `save_scene_data` already move panel scene state toward vault-scoped workspace storage.

The current recovery work keeps FGU aligned with this direction by recording imports and exports as workspace object references rather than inventing a canvas-specific state model.

## First Slice

Before building a canvas UI:

1. Define stable workspace object identity and supported object kinds.
2. Define view presentation state: docked, floating, canvas card, pinned widget, collapsed, position, and size.
3. Store layout profiles under the active vault `.ceres` workspace directory.
4. Make Command Center panels read/write the shared model where practical.
5. Only then prototype an Infinite Table panel against the same object store.

## AI Delegation

| Tool | Best responsibility | Avoid assigning |
|---|---|---|
| Codex | Repo-grounded implementation, tests, verification, and wiring through existing PyQt/Pantheon patterns | Broad visual redesign without codebase constraints |
| Claude Sonnet 4.6 | Architecture critique, object model review, risk analysis, and staged refactor planning | Direct repo mutation unless its output is translated into concrete patches |
| Cursor auto | Small, well-scoped UI slices after interfaces are locked, such as a first canvas prototype or panel polish | Cross-cutting state-model decisions or broad rewrites |

## Handoff Rule

Architecture decisions should land in docs first, then Codex should turn them into small tested implementation slices. Cursor should receive narrow briefs with exact files, expected UI behavior, and verification commands.
