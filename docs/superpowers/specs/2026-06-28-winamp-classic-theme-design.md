# Winamp Classic Theme Design

## Goal

Make the current Project Ceres desktop theme look much closer to the original Winamp classic skin shown in the user-provided reference image.

## Selected Direction

The user selected option C, "Full Replica Energy." The app should lean into the recognizable Winamp look rather than stopping at a palette pass.

## Visual Requirements

- Use near-black content wells for chat, lists, consoles, text areas, and playlist-like surfaces.
- Use steel-blue and graphite chrome for panels, dock title bars, menus, tabs, buttons, and framed controls.
- Use bright green LCD-style text for primary text and active list content.
- Use yellow/gold for slider handles, progress chunks, focus accents, and meter-like highlights.
- Prefer square or nearly square controls with beveled borders over rounded modern cards.
- Keep high contrast and readable text at the current app scale.

## Scope

The implementation should update:

- `ui/theme.py` as the global palette and QSS source.
- The most visible local hardcoded styles that would otherwise keep the old crimson/purple theme alive:
  - chat header, input bar, bubbles, and send controls in `ui/panels/chat_panel.py`
  - mixer row frames, slider helpers, and mute buttons in `ui/panels/mixer_panel.py`
  - equalizer control frame and label treatment in `ui/panels/equalizer_panel.py`

The implementation should not change:

- dock layout behavior
- saved geometry behavior
- audio behavior
- command behavior
- application data or settings schemas

## Testing

Add a narrow theme regression test that checks the Winamp palette constants and QSS markers. Then run the GUI constructor smoke test and compile checks for the touched UI modules.
