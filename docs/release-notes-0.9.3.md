# MORICE 0.9.3 — simpler Projects and Experiments

Opening Projects now selects Builder mode. Explicit Build/Ask intent takes priority over keyword shortcuts, so a request to create a simulator application reaches file generation rather than being mistaken for a research experiment. Builder resolves the same bundled/default backend as ordinary chat when no custom model is selected.

Projects presents folder selection, a Build/Ask choice, review and save, files, output, updates and an inline browser preview. Access and lookup controls remain under Build settings. The existing verified browser is reparented for previews; no second browser or execution authority is introduced. Stop build uses the existing cancellation token. Compact Project reviews scroll without squeezing Save, and experiment Run controls stay visible while the inputs scroll.

Research has a plain-language experiment entry and a model/values form. Review shows the actual bounded plan before Run. Results and input errors remain visible in Research, while JSON specifications and technical diagnostics are under Advanced. Primary navigation is shorter, with labels for new sessions and all remaining destinations under More.

Local Python modules and relative imports no longer become inferred pip dependencies. Automatic proposals preserve complete goals that fit the shared task budget, and explicitly report oversized goals instead of silently dropping later requirements. Icon binding tolerates unsupported plugin icon names using the existing authored fallback. User/permission/environment verification blocks no longer trigger a source-repair model wait; fresh retries can still repair actual code failures. A delayed GPU detection callback now ignores closing windows.

See the [usage guide and concrete technical constraints](simple-workspaces.md) and [workflow validation](workspace-validation-0.9.3.md). Existing permission handling, verification, process ownership, bounded workers, resource leases and Phase 2 agent/runtime contracts remain in force.

Windows and Python packages require separately installed compatible models and adequate RAM/VRAM for inference. No new real-weight inference or physical Android/provider certification is claimed by this workflow update. Earlier validation limitations remain in the existing phase reports.
