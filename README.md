# UniClick - Multi-Target Sequence & Timer

A desktop multi-target auto clicker featuring a clean, responsive dark UI, circular tactical screen pins, multi-monitor intelligence, and anti-detection humanization.

---

## Highlights & Features

1. **Tactical Circular Target Pins (`target_pin.py`)**:
   - **True Circular Cutout**: Outer corners are 100% transparent while the circular reticle interior is solid and draggable from any pixel inside the disc.
   - **Elastic Pop-In & Click Ripple Feedback**: Pins pop into place with a smooth scale animation on spawn/gather, pulse when scrolled, and emit a 100% click-through expanding ring ripple whenever a step fires during a run.
   - **Color-Coded Sequence Roles**:
     - **Emerald Green (`#1`)**: First target in the sequence.
     - **Cyber Blue (`#2..#N-1`)**: Intermediate sequence targets.
     - **Amber Gold (`#N`)**: Final target before the cycle loops.
     - **Slate Gray**: Disabled targets.
   - **Live Floating HUD Tooltip & Direct Shortcuts**:
     - Hovering a pin (or its step card in the UI) highlights the reticle and shows its live `(X, Y)` coordinates and delay right above it.
     - **Scroll Mouse Wheel** directly on any pin to adjust its delay (`±0.10s`) on the fly.
     - **Right-Click** on any pin to delete it immediately.

2. **Smart Multi-Monitor Target Acquisition**:
   - **`[🕵️ Snipe on Screen]`**: Interactive cross-monitor Snipe Mode—a floating coordinate HUD follows your mouse across any monitor; simply **Left-Click** anywhere on your screen to drop a pin!
   - **`[＋ Spawn Pin]`**: Spawns a new pin near the **center of your active monitor** (cascaded diagonally so pins never stack on top of each other or cover UI buttons).
   - **`F7` Instant Drop**: Hover over any point on any monitor and press `F7` to drop a pin at your cursor with a crisp audio cue.
   - **`[📍 Gather pins here]`**: One click brings all pins from any monitor/resolution neatly to the center of your current screen with a synchronized pop animation.

3. **Clean, Friendly & Satisfying Interface (`app_ui.py`, `theme.py`, `toast.py`, `ui_widgets.py`)**:
   - **Pulsing Status Pill & Keycap Banner**: Live status indicator with a pulsing dot while running, plus keycap-style shortcut hints and real-time multi-monitor cursor readout.
   - **Streamlined Step Cards**: Two-line target cards with inline label editing, step enable/disable switches, click type (`Left` / `Double` / `Right`), burst repeat (`x1..x10`), and flicker-free hover sync with on-screen pins.
   - **Collapsible Settings Sections**: Right-hand panel organized into collapsible sections (*Click Interval*, *Active Timer*, *Repeat Cycles*, *Profiles & Presets*, *Activity Log*) with live summary badges in every header.
   - **Slide-Up Toast Notifications & Multi-Note Sound Cues**: Non-blocking slide-up toasts (`ToastManager`) and pleasant multi-note audio chimes (`play_sound`) for adding pins, starting, pausing, stopping, and completing runs.
   - **Compact Mini Mode (`540x88`)**: Shrinks the full app into a sleek always-on-top floating bar (`[🗕 Mini]`) with live status, timer, progress bar, and transport controls.

4. **Anti-Cheat Humanizer & Multi-Monitor "Ghost Click" (`engine.py`)**:
   - **Click Radius (`± px`)**: Randomizes each click within a small pixel radius (e.g., `±4 px`) so clicks never hit the exact same pixel twice.
   - **Time Jitter (`± s`)**: Adds subtle human timing variance to every interval.
   - **👻 Ghost Click (Return Cursor)**: Keep your automated app running on Monitor 2 while working on Monitor 1—each time a step fires, the mouse clicks on Monitor 2 and immediately returns to where your hand was on Monitor 1.

---

## Quick Start

- **Run from Source**: Double-click `run.bat` or run `python main.py`
- **Standalone Executable**: Run `dist\UniClick.exe` (or rebuild via `build_exe.bat`)
- **Run Unit Tests**: `python -m unittest discover tests`
