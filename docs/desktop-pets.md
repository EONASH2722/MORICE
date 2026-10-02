# MORICE desktop pets

Desktop pets are an optional, low-overhead companion process. The process loads
PySide and pet metadata only; it does not start the language model, agent
planner, network retrieval, microphone, or voice pipeline.

![MORICE desktop-pet settings](screenshots/desktop-pets/22-pet-settings-panel.png)

## Launcher behavior

A normal primary-button click immediately plays the pet's reaction and sends a
local `open_morice` or `open_chat` command. The primary MORICE process restores
its existing window, repairs its position only if the saved monitor no longer
exists, raises it, and requests focus. If no main process exists, the pet starts
one process and polls the local activation endpoint until its window is ready.
Rapid clicks share the same pending launch.

Pointer classification uses Qt's Windows/DPI-aware drag distance and drag-time
settings. Passing the movement threshold makes the gesture a drag permanently;
releasing it cannot open MORICE.

MORICE itself owns a per-user lock and local command endpoint. A second launch
hands its action to the primary process before runtime/model startup, then
exits. This is the final duplicate-process guard even if two independent
launchers race.

## Settings

The MORICE panel contains the following persistent controls:

- Show desktop pet
- Pet (Iron Man — Mark 42, Spider-Man, Horse, Skeleton, Dog, or Cat)
- Pet size
- Pet animation speed: Slow, Normal, or Fast
- Pet click action: Open MORICE, Open MORICE Chat, or Do nothing
- Pet special events: Off, Low, Normal, High, or Showcase (demo)
- Hide pet during fullscreen/games (on by default)
- Allow pet dragging and interaction
- Remove Pet

The resident host intentionally remains available when the main window exits,
so the character can launch MORICE later. `Remove Pet` disables the setting and
asks that host to close; a per-user lock prevents duplicate pet hosts.

## Animation and interaction

Every pet has a data-declared set of behavior states and a shared animation
controller. Ground pets settle onto the current display work area and use
bounded walk, play, reaction, and sleep cycles. Flying and acrobatic pets use a
stable vertical anchor, so hovering and swinging cannot accumulate positional
drift over time.

| Pet | Bundled behaviors |
| --- | --- |
| Iron Man — Mark 42 | Full-screen flight patrol; Mark 42 armor-off/coffee/reassembly; rogue-drone chase and directed repulsor defeat; arc-reactor click flash |
| Spider-Man | Perch and pendulum web swing; temporary symbiote transform/removal; masked tech-raider chase, web and cocoon; eye click reaction |
| Dog | Walk/play/sleep plus ball-ready, chase, return and tail-wag celebration |
| Cat | Walk/play plus tiny-bed deep sleep, breathing, ear/tail movement and stretch |
| Horse | Trot/play plus grass grazing, rear and full-speed gallop |
| Skeleton | Walk/rattle plus multi-stage bone collapse, scatter and reform |

The click reaction and MORICE activation are started together. The animation
does not delay window restoration. Dragging is classified through Qt's
OS/DPI-aware start distance and start time, then hands the pet to its drag or
escape state without emitting an application-open command.

## Fullscreen and performance

The host checks the foreground window against its monitor bounds at a coarse
650 ms interval. During a fullscreen game or video it hides the overlay and
stops the animation timer, leaving no invisible click target. Rendering uses a
20 FPS coarse timer, nearest-neighbor/block drawing, a small shaped overlay, and
no continuous whole-screen redraw.

## Asset structure

Pet definitions live under `morice/assets/pets/<pet_id>/definition.json`.
Definitions declare the display name, renderer, movement profile, click
feedback, accent, and supported sprite-pack slots. The bundled visuals are
original procedural development art, not scraped game or comic assets.

To add a pet:

1. Add a definition directory and JSON file.
2. Register the stable ID in `SUPPORTED_PETS` and the settings normalizer.
3. Add a procedural renderer or a licensed sprite renderer matching the
   definition's `renderer` value.
4. Add the pet to the selection list and tests.

The click/drag recognizer, launcher, fullscreen guard, monitor repair, and
single-instance code are shared by every pet and do not need pet-specific
changes.

## Rare-event scheduling

Special scenes are local deterministic UI sequences; they never invoke an LLM,
planner, voice service, or network call. Every scene has its own randomized
interval, probability, priority, and persisted next-due timestamp. Restarting
MORICE therefore cannot repeatedly retrigger an event. Only one major scene can
run at a time, and grabbing the pet or entering fullscreen cancels the current
scene and returns to normal behavior rather than replaying it later.

**Normal** is the intended everyday frequency. **Low** approximately doubles
the wait, **High** shortens it, and **Showcase (demo)** compresses waits to a few
seconds for judging or development. **Off** disables every rare scene. Combat
is stylized and non-graphic: Iron Man faces an original rogue drone and
Spider-Man faces an original masked tech raider. Defeated enemies fade away and
never leave an input-blocking overlay.

## Transparent showcase assets

Showcase captures are optional local development outputs, not guaranteed bundled
documentation assets. The current art is procedural; film-accurate anatomy, armor
detail, and fully polished flight/combat motion remain unfinished. To generate
transparent inspection renders locally, run:

```powershell
python scripts\render_pet_showcase.py
```

The render script also serves as a quick visual-regression pass: it instantiates
the production overlay and exercises idle, motion, special, sleep, escape, and
click-reaction states rather than reproducing them in a separate mock.
