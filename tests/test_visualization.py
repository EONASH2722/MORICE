import os
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MORICE_START_AWAKE", "1")
os.environ.setdefault("MORICE_REDUCE_MOTION", "1")

from PySide6.QtWidgets import QApplication

from morice.pyside_app import (
    InlineBiologyWorkspace,
    InlineChartWorkspace,
    InlineDataStructureWorkspace,
    InlineDiagramWorkspace,
    InlineDocumentWorkspace,
    InlineGraphWorkspace,
    InlineMoleculeWorkspace,
    InlinePhysicsWorkspace,
    InlineSceneWorkspace,
    MoriceWindow,
    PhysicsCanvas,
    SurfaceCanvas,
    _needs_web_rich_text,
    _web_assets_path,
)
from morice.project_builder import (
    ProjectIntentError,
    build_project_fallback_manifest,
)
from morice.project_runtime import ProjectValidationError
from morice.science_engine import Particle, PhysicsArtifact
from morice.visualization import VisualizationManager


class VisualizationManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = VisualizationManager()

    def tearDown(self):
        self.manager.shutdown()

    def _render(self, prompt):
        decision = self.manager.decide(prompt)
        self.assertIsNotNone(decision)
        request = self.manager.create_request(prompt, decision)
        progress = []
        result = self.manager.render(
            request,
            lambda stage, detail, percent: progress.append((stage, detail, percent)),
        )
        self.assertTrue(progress)
        self.assertEqual(progress[-1][2], 100)
        return result

    def test_graph_is_real_validated_and_cached(self):
        prompt = "Plot y = x^3 - 6x^2 + 9x + 2 and mark the inflection point."
        first = self._render(prompt)
        second = self._render(prompt)

        self.assertTrue(first.ok)
        self.assertIsNotNone(first.artifact.graph)
        self.assertGreater(len(first.artifact.graph.series[0].x), 100)
        self.assertTrue(second.ok)
        self.assertTrue(second.from_cache)

    def test_physics_request_produces_requested_bodies(self):
        result = self._render(
            "Create a simulation of 500 particles in a box with elastic collisions and gravity."
        )

        self.assertTrue(result.ok)
        self.assertIsNotNone(result.artifact.physics)
        self.assertEqual(len(result.artifact.physics.particles), 500)

    def test_surface_request_is_validated(self):
        result = self._render("Render z=sin(x)*cos(y) as a 3D surface.")

        self.assertTrue(result.ok)
        self.assertIsNotNone(result.artifact.graph.surface)
        self.assertEqual(
            result.artifact.graph.instruction["parameters"]["views"],
            ["2d", "3d"],
        )

    def test_data_structure_request_does_not_collapse_into_math_graph(self):
        result = self._render(
            "Visualize Binary Search Tree AVL Tree Graph Linked List Queue Stack "
            "Hash Table. For every structure support Insert Delete Search, "
            "highlight operations, animated transitions, and complexity display."
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.renderer_id, "computer-science.data-structures")
        self.assertEqual(result.artifact.kind, "data-structures")
        self.assertEqual(len(result.artifact.data_structures.structures), 7)

    def test_biology_and_astronomy_route_to_their_own_engines(self):
        biology = self._render("Render a DNA double helix with 2D and 3D views.")
        astronomy = self._render(
            "Visualize the solar system with orbital motion, labels, and play pause."
        )

        self.assertTrue(biology.ok)
        self.assertEqual(biology.renderer_id, "biology.educational")
        self.assertEqual(biology.artifact.biology.model_type, "dna")
        self.assertEqual(
            biology.artifact.biology.instruction["parameters"]["views"],
            ["2d", "3d"],
        )
        self.assertTrue(astronomy.ok)
        self.assertEqual(astronomy.renderer_id, "physics.simulation")

    def test_curated_chemistry_renderer_is_real_and_validated(self):
        result = self._render("Render an interactive 3D VSEPR model of SF4.")

        self.assertTrue(result.ok)
        molecule = result.artifact.chemistry
        self.assertEqual(molecule.formula, "SF4")
        self.assertEqual(molecule.geometry, "seesaw")
        self.assertEqual(molecule.electron_geometry, "trigonal bipyramidal")
        self.assertEqual(molecule.central_lone_pairs, 1)
        self.assertEqual(len(molecule.atoms), 5)
        self.assertEqual(len(molecule.bonds), 4)
        self.assertEqual(
            molecule.instruction["parameters"]["views"],
            ["2d", "3d"],
        )

    def test_unknown_molecule_fails_without_fake_output(self):
        result = self._render("Render an interactive 3D VSEPR model of IF7.")

        self.assertFalse(result.ok)
        self.assertIsNone(result.artifact)
        self.assertIn("could not parse", result.error)

    def test_known_diagram_is_structured_and_validated(self):
        result = self._render("Show the TCP three-way handshake diagram.")

        self.assertTrue(result.ok)
        diagram = result.artifact.diagram
        self.assertEqual(diagram.title, "TCP three-way handshake")
        self.assertEqual(len(diagram.nodes), 4)
        self.assertEqual(len(diagram.edges), 3)

    def test_numeric_chart_preserves_prompt_values(self):
        result = self._render(
            "Render a bar chart of Apples: 12, Bananas: 7, Cherries: 19."
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.renderer_id, "data.chart")
        self.assertEqual(result.artifact.chart.chart_type, "bar")
        self.assertEqual(
            [(point.label, point.y) for point in result.artifact.chart.points],
            [("Apples", 12.0), ("Bananas", 7.0), ("Cherries", 19.0)],
        )

    def test_scatter_chart_preserves_coordinate_pairs(self):
        result = self._render(
            "Show a scatter plot of (1, 4), (2, 8), (3.5, -2)."
        )

        self.assertTrue(result.ok)
        self.assertEqual(
            [(point.x, point.y) for point in result.artifact.chart.points],
            [(1.0, 4.0), (2.0, 8.0), (3.5, -2.0)],
        )

    def test_supported_generic_scene_has_valid_2d_and_3d_geometry(self):
        result = self._render(
            "Render an interactive 3D drone model with labeled components."
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.renderer_id, "model.schematic-3d")
        scene = result.artifact.scene
        self.assertEqual(scene.scene_type, "drone")
        self.assertEqual(scene.instruction["parameters"]["views"], ["2d", "3d"])
        self.assertEqual(len(scene.primitives), 5)
        self.assertTrue(
            all(value > 0 for primitive in scene.primitives for value in primitive.size)
        )

    def test_every_curated_scene_family_validates(self):
        for scene_type in (
            "robot",
            "drone",
            "car",
            "aircraft",
            "ship",
            "building",
            "bridge",
            "engine",
            "CPU",
            "GPU",
            "motherboard",
            "camera",
            "watch",
        ):
            with self.subTest(scene_type=scene_type):
                result = self._render(
                    f"Render an interactive 3D {scene_type} with labeled components."
                )
                self.assertTrue(result.ok)
                self.assertEqual(
                    result.artifact.scene.instruction["parameters"]["views"],
                    ["2d", "3d"],
                )

    def test_domain_diagram_templates_cover_database_ai_security_and_biology(self):
        for prompt, title in (
            ("Show an ER diagram.", "Entity-relationship model"),
            ("Visualize transformer architecture.", "Transformer processing path"),
            ("Draw the AES encryption flow.", "AES round structure"),
            ("Show protein synthesis as a diagram.", "Protein synthesis"),
        ):
            with self.subTest(prompt=prompt):
                result = self._render(prompt)
                self.assertTrue(result.ok)
                self.assertEqual(result.artifact.diagram.title, title)
                self.assertGreaterEqual(len(result.artifact.diagram.nodes), 5)

    def test_extended_domain_diagram_matrix_validates(self):
        prompts = (
            "Show the TLS handshake diagram.",
            "Visualize packet routing.",
            "Draw firewall flow.",
            "Show virtual memory address translation.",
            "Visualize CPU scheduling.",
            "Draw a deadlock resource allocation graph.",
            "Show an SQL join diagram.",
            "Visualize a database transaction lifecycle.",
            "Draw a B+ tree database index.",
            "Show gradient descent optimization steps.",
            "Visualize RSA encryption.",
            "Draw a digital signature verification flow.",
            "Show the cell cycle.",
            "Visualize a food chain.",
            "Draw an RC circuit diagram.",
            "Show the water cycle.",
            "Visualize plate tectonics.",
            "Draw the supply and demand relationships.",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                result = self._render(prompt)
                self.assertTrue(result.ok, result.error)
                self.assertEqual(result.renderer_id, "diagram.structured")
                self.assertGreaterEqual(len(result.artifact.diagram.nodes), 4)

    def test_user_supplied_timeline_is_rendered_without_invented_events(self):
        result = self._render(
            "Render a timeline: 1991: Web released, 2007: Smartphones expand, "
            "2022: Generative AI adoption."
        )

        self.assertTrue(result.ok)
        labels = [node.label for node in result.artifact.diagram.nodes]
        self.assertEqual(
            labels,
            [
                "1991: Web released",
                "2007: Smartphones expand",
                "2022: Generative AI adoption.",
            ],
        )

    def test_unknown_generic_3d_object_still_fails_honestly(self):
        result = self._render("Render an interactive 3D fictional flux orb.")

        self.assertFalse(result.ok)
        self.assertIsNone(result.artifact)
        self.assertIn("not installed", result.error)

    def test_local_document_path_produces_validated_preview_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "research notes.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("measured value: 42\n")
            result = self._render(f'Show this file: "{path}"')

        self.assertTrue(result.ok)
        self.assertEqual(result.renderer_id, "viewer.document")
        self.assertEqual(result.artifact.document.path, path)
        self.assertGreater(result.artifact.document.size_bytes, 0)

    def test_invalid_expression_never_claims_success(self):
        result = self._render("Plot y = os.system(x)")

        self.assertFalse(result.ok)
        self.assertIsNone(result.artifact)
        self.assertIn("failed", result.status)

    def test_unsupported_fluid_is_an_honest_failure(self):
        result = self._render("Simulate an SPH fluid in a tank.")

        self.assertFalse(result.ok)
        self.assertIsNone(result.artifact)
        self.assertIn("could not parse", result.error)

    def test_fake_visual_placeholder_is_removed(self):
        cleaned = self.manager.sanitize_model_reply("[A graph is shown on screen.]")

        self.assertIn("No visualization was rendered", cleaned)
        self.assertNotIn("[A graph", cleaned)

    def test_rich_renderer_detects_math_and_has_local_assets(self):
        self.assertTrue(_needs_web_rich_text(r"Use \(x^2+1\)."))
        self.assertTrue(_needs_web_rich_text("```python\nprint(1)\n```"))
        for name in (
            "katex.min.js",
            "katex.min.css",
            "auto-render.min.js",
            "markdown-it.min.js",
            "highlight.min.js",
        ):
            self.assertTrue(os.path.isfile(os.path.join(_web_assets_path(), name)))


class InlineVisualizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MoriceWindow()
        self.window.awake = True
        self.window._set_chat_mode("normal")

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def _wait_for_jobs(self, timeout=5.0):
        deadline = time.monotonic() + timeout
        while self.window.visualization_futures and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertFalse(self.window.visualization_futures)

    def test_desktop_identity_is_morice_with_a_real_icon(self):
        self.assertEqual(self.window.windowTitle(), "MORICE")
        self.assertFalse(self.window.windowIcon().isNull())
        self.assertEqual(self.app.applicationDisplayName(), "MORICE")

    def test_custom_maximize_uses_available_desktop_geometry(self):
        self.window.show()
        self.app.processEvents()
        available = self.window.screen().availableGeometry()

        self.window.title_bar._toggle_maximize()
        self.app.processEvents()

        self.assertTrue(self.window._custom_maximized)
        self.assertEqual(self.window.geometry().top(), available.top())
        self.assertEqual(self.window.geometry().bottom(), available.bottom())
        if available.width() >= self.window.minimumWidth():
            self.assertEqual(self.window.geometry().left(), available.left())
            self.assertEqual(self.window.geometry().right(), available.right())

    def test_graph_replaces_progress_card_inside_chat(self):
        self.assertTrue(self.window._handle_science_request("Plot y=(x-1)^2"))
        self._wait_for_jobs()

        workspaces = self.window.chat_list.findChildren(InlineGraphWorkspace)
        self.assertEqual(len(workspaces), 1)
        self.assertFalse(self.window.workspace_panel.isVisible())

        with tempfile.TemporaryDirectory() as folder:
            canvas = workspaces[0].canvas
            png = os.path.join(folder, "graph.png")
            svg = os.path.join(folder, "graph.svg")
            pdf = os.path.join(folder, "graph.pdf")
            self.assertTrue(canvas.export_png(png))
            self.assertTrue(canvas.export_svg(svg))
            self.assertTrue(canvas.export_pdf(pdf))
            for path in (png, svg, pdf):
                self.assertGreater(os.path.getsize(path), 100)

    def test_molecule_replaces_progress_card_and_switches_views(self):
        self.assertTrue(
            self.window._handle_science_request("Render the molecular geometry of SF4.")
        )
        self._wait_for_jobs()

        workspaces = self.window.chat_list.findChildren(InlineMoleculeWorkspace)
        self.assertEqual(len(workspaces), 1)
        workspace = workspaces[0]
        original_atoms = [
            (atom.x, atom.y, atom.z) for atom in workspace.artifact.atoms
        ]
        workspace.dimension_select.setCurrentText("2D")
        self.app.processEvents()
        self.assertEqual(workspace.canvas.view_mode, "2d")
        workspace.dimension_select.setCurrentText("3D")
        self.app.processEvents()
        self.assertEqual(workspace.canvas.view_mode, "3d")
        self.assertEqual(
            original_atoms,
            [(atom.x, atom.y, atom.z) for atom in workspace.artifact.atoms],
        )

    def test_biology_workspace_renders_real_geometry_and_switches_views(self):
        self.assertTrue(
            self.window._handle_science_request(
                "Render a DNA double helix with animated twisting and labels."
            )
        )
        self._wait_for_jobs()
        workspace = self.window.chat_list.findChildren(InlineBiologyWorkspace)[0]

        self.assertGreater(len(workspace.canvas.artifact.points), 20)
        workspace.dimension_select.setCurrentText("2D")
        self.assertEqual(workspace.canvas.view_mode, "2d")
        workspace.dimension_select.setCurrentText("3D")
        self.assertEqual(workspace.canvas.view_mode, "3d")

    def test_data_structure_workspace_runs_real_operations(self):
        prompt = (
            "Visualize Binary Search Tree, AVL Tree, Graph, Linked List, Queue, "
            "Stack and Hash Table with Insert Delete Search and complexity display."
        )
        self.assertTrue(self.window._handle_science_request(prompt))
        self._wait_for_jobs()
        workspace = self.window.chat_list.findChildren(InlineDataStructureWorkspace)[0]

        self.assertEqual(workspace.structure_select.count(), 7)
        workspace.value_input.setText("25")
        workspace._operate("insert")
        self.assertIn(25, workspace._current_values())
        workspace._operate("search")
        self.assertIn(25, workspace.canvas.highlighted)
        self.assertIn("Complexity", workspace.complexity.text())
        workspace.structure_select.setCurrentText("AVL Tree")
        self.assertEqual(
            workspace.canvas._balanced_tree(workspace._current_values())[0],
            40,
        )
        workspace.structure_select.setCurrentText("Queue")
        queue_before = list(workspace._current_values())
        workspace._operate("delete")
        self.assertEqual(workspace._current_values(), queue_before[1:])
        workspace.structure_select.setCurrentText("Stack")
        stack_before = list(workspace._current_values())
        workspace._operate("delete")
        self.assertEqual(workspace._current_values(), stack_before[:-1])

    def test_diagram_replaces_progress_card_inside_chat(self):
        self.assertTrue(
            self.window._handle_science_request("Show the OSI model diagram.")
        )
        self._wait_for_jobs()

        workspaces = self.window.chat_list.findChildren(InlineDiagramWorkspace)
        self.assertEqual(len(workspaces), 1)
        self.assertEqual(len(workspaces[0].artifact.nodes), 7)

    def test_chart_replaces_progress_card_and_exports_real_files(self):
        self.assertTrue(
            self.window._handle_science_request(
                "Render a pie chart of Design: 35, Code: 45, Test: 20."
            )
        )
        self._wait_for_jobs()
        workspace = self.window.chat_list.findChildren(InlineChartWorkspace)[0]
        self.assertEqual(len(workspace.canvas.artifact.points), 3)

        with tempfile.TemporaryDirectory() as folder:
            for extension, exporter in (
                ("png", workspace.canvas.export_png),
                ("svg", workspace.canvas.export_svg),
                ("pdf", workspace.canvas.export_pdf),
            ):
                path = os.path.join(folder, f"chart.{extension}")
                self.assertTrue(exporter(path))
                self.assertGreater(os.path.getsize(path), 100)

    def test_scene_replaces_progress_card_and_switches_views(self):
        self.assertTrue(
            self.window._handle_science_request(
                "Render a 3D robot with labeled components."
            )
        )
        self._wait_for_jobs()
        workspace = self.window.chat_list.findChildren(InlineSceneWorkspace)[0]
        self.assertEqual(workspace.artifact.scene_type, "robot")
        workspace.dimension_select.setCurrentText("2D")
        self.assertEqual(workspace.canvas.view_mode, "2d")
        workspace.dimension_select.setCurrentText("3D")
        self.assertEqual(workspace.canvas.view_mode, "3d")

    def test_document_replaces_progress_card_with_real_file_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "preview.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('{"status": "ready", "value": 42}')
            self.assertTrue(
                self.window._handle_science_request(f'Preview local file "{path}"')
            )
            self._wait_for_jobs()
            workspace = self.window.chat_list.findChildren(InlineDocumentWorkspace)[0]
            self.assertEqual(workspace.preview.current_path, path)
            self.assertIn("loaded", workspace.status.text().lower())

    def test_physics_replaces_progress_card_inside_chat(self):
        self.assertTrue(
            self.window._handle_science_request(
                "Simulate 80 particles with gravity and elastic collisions."
            )
        )
        self._wait_for_jobs()

        workspaces = self.window.chat_list.findChildren(InlinePhysicsWorkspace)
        self.assertEqual(len(workspaces), 1)
        self.assertEqual(len(workspaces[0].canvas.artifact.particles), 80)
        self.assertFalse(self.window.workspace_panel.isVisible())

    def test_physics_replay_and_json_state_are_real(self):
        self.assertTrue(
            self.window._handle_science_request(
                "Simulate 24 particles without gravity and with elastic collisions."
            )
        )
        self._wait_for_jobs()
        canvas = self.window.chat_list.findChildren(InlinePhysicsWorkspace)[0].canvas
        canvas.set_running(False)
        before = [
            (particle.x, particle.y, particle.vx, particle.vy)
            for particle in canvas.artifact.particles
        ]
        canvas.step_once()
        after = [
            (particle.x, particle.y, particle.vx, particle.vy)
            for particle in canvas.artifact.particles
        ]
        self.assertNotEqual(before, after)
        canvas.step_back()
        restored = [
            (particle.x, particle.y, particle.vx, particle.vy)
            for particle in canvas.artifact.particles
        ]
        self.assertEqual(before, restored)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "state.json")
            self.assertTrue(canvas.export_json(path))
            with open(path, "r", encoding="utf-8") as handle:
                payload = __import__("json").load(handle)
            self.assertEqual(payload["schema"], "morice.physics-state.v1")
            self.assertEqual(len(payload["particles"]), 24)

    def test_hidden_physics_canvas_does_not_consume_simulation_frames(self):
        self.assertTrue(
            self.window._handle_science_request(
                "Simulate 40 particles with gravity, velocity vectors, and trails."
            )
        )
        self._wait_for_jobs()
        workspace = self.window.chat_list.findChildren(InlinePhysicsWorkspace)[0]

        self.assertTrue(workspace.canvas.show_trails)
        before = workspace.canvas._frames
        workspace.hide()
        workspace.canvas.step()
        self.assertEqual(workspace.canvas._frames, before)

    def test_project_workspace_keeps_review_panel_readable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "main.py")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("print('ready')\n")
            self.window.project_folder = folder
            self.window._set_chat_mode("project")
            self.window._on_project_changes_ready(
                "Updated main.py",
                "<p><span style='color:#7cf7b5'>+ print('ready')</span></p>",
            )
            self.app.processEvents()

            self.assertFalse(self.window.changes_content.isHidden())
            self.assertFalse(self.window.changes_minimized)
            self.assertGreaterEqual(self.window.changes_panel.width(), 440)
            self.assertFalse(self.window.changes_close_btn.isHidden())
            self.window._set_project_workspace_tab(0)
            self.assertGreaterEqual(
                self.window.project_file_tree.topLevelItem(0).childCount(),
                1,
            )

            self.window._close_changes_panel()
            self.app.processEvents()
            self.assertTrue(self.window.changes_panel_dismissed)
            self.assertFalse(
                self.window._panel_target_visibility[self.window.changes_panel]
            )

            self.window._refresh_mode_panel()
            self.app.processEvents()
            self.assertFalse(
                self.window._panel_target_visibility[self.window.changes_panel]
            )

            self.window._on_project_changes_ready(
                "Updated main.py again",
                "<p><span style='color:#7cf7b5'>+ print('again')</span></p>",
            )
            self.app.processEvents()
            self.assertFalse(self.window.changes_panel_dismissed)
            self.assertTrue(
                self.window._panel_target_visibility[self.window.changes_panel]
            )

    def test_project_manifest_writes_validated_files_atomically(self):
        with tempfile.TemporaryDirectory() as folder:
            self.window.project_folder = folder
            result = self.window._apply_project_manifest(
                {
                    "summary": "Built test project.",
                    "files": [
                        {
                            "path": "main.py",
                            "content": "def main():\n    return 0\n\nif __name__ == '__main__':\n    raise SystemExit(main())\n",
                        },
                        {
                            "path": "config.json",
                            "content": '{"ready": true}\n',
                        },
                    ],
                }
            )

            self.assertTrue(result["validated"])
            with open(
                os.path.join(folder, "config.json"),
                encoding="utf-8",
            ) as config_file:
                self.assertEqual(config_file.read(), '{"ready": true}\n')
            self.assertFalse(
                any(name.startswith(".morice-write-") for name in os.listdir(folder))
            )

    def test_project_patch_review_apply_and_undo_flow_is_real(self):
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "main.py")
            with open(target, "w", encoding="utf-8") as source:
                source.write("print('before')\n")
            self.window.project_folder = folder
            result = self.window._apply_project_manifest(
                {
                    "summary": "Update main.",
                    "files": [
                        {
                            "path": "main.py",
                            "content": "print('after')\n",
                        }
                    ],
                },
                preview_only=True,
            )
            self.window._on_project_changes_ready(
                result["summary"],
                result["diff_html"],
            )

            self.assertTrue(result["pending"])
            self.assertTrue(self.window.changes_apply_btn.isEnabled())
            with open(target, encoding="utf-8") as source:
                self.assertEqual(source.read(), "print('before')\n")

            self.window._apply_pending_project_patch()
            deadline = time.monotonic() + 5
            while self.window.pending_project_patch and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
            self.app.processEvents()
            with open(target, encoding="utf-8") as source:
                self.assertEqual(source.read(), "print('after')\n")
            self.assertTrue(self.window.changes_undo_btn.isEnabled())

            self.window._undo_last_project_patch()
            deadline = time.monotonic() + 5
            while self.window.last_project_undo_id and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
            self.app.processEvents()
            with open(target, encoding="utf-8") as source:
                self.assertEqual(source.read(), "print('before')\n")

    def test_invalid_project_manifest_cannot_replace_existing_source(self):
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "main.py")
            original = "print('stable')\n"
            with open(target, "w", encoding="utf-8") as source_file:
                source_file.write(original)
            self.window.project_folder = folder

            with self.assertRaises(ProjectValidationError):
                self.window._apply_project_manifest(
                    {
                        "files": [
                            {
                                "path": "main.py",
                                "content": "def broken(:\n",
                            }
                        ]
                    }
                )

            with open(target, "r", encoding="utf-8") as source_file:
                self.assertEqual(source_file.read(), original)

    def test_project_manifest_semantics_are_checked_before_any_write(self):
        with tempfile.TemporaryDirectory() as folder:
            self.window.project_folder = folder
            request = "Build a fully playable Flappy Bird 3D game."
            bad_manifest = {
                "files": [
                    {
                        "path": "index.html",
                        "content": "<h1>Build a fully playable Flappy Bird 3D game</h1>",
                    }
                ]
            }

            with self.assertRaises(ProjectIntentError):
                self.window._apply_project_manifest(bad_manifest, request)

            self.assertEqual(os.listdir(folder), [])

    def test_project_manifest_writes_validated_flappy_game(self):
        with tempfile.TemporaryDirectory() as folder:
            self.window.project_folder = folder
            request = "Build a polished Flappy Bird 3D game for the browser."
            manifest = build_project_fallback_manifest(request, folder)

            result = self.window._apply_project_manifest(manifest, request)

            self.assertTrue(result["validated"])
            self.assertTrue(os.path.isfile(os.path.join(folder, "index.html")))
            self.assertTrue(os.path.isfile(os.path.join(folder, "game.js")))
            self.assertIn("game.js", result["changed"])

    def test_vnext_visualization_is_normal_chat_only(self):
        self.window._set_chat_mode("project")

        self.assertFalse(self.window._handle_science_request("Plot y=x^2"))
        self.assertEqual(
            self.window.chat_list.findChildren(InlineGraphWorkspace),
            [],
        )

    def test_surface_workspace_exposes_real_2d_and_3d_views(self):
        self.assertTrue(self.window._handle_science_request("Plot 3D z=x^2+y^2"))
        self._wait_for_jobs()
        workspace = self.window.chat_list.findChildren(InlineGraphWorkspace)[0]

        self.assertIsInstance(workspace.canvas, SurfaceCanvas)
        self.assertEqual(workspace.dimension_select.count(), 2)
        workspace.dimension_select.setCurrentText("2D")
        self.assertEqual(workspace.canvas.view_mode, "2d")
        workspace.dimension_select.setCurrentText("3D")
        self.assertEqual(workspace.canvas.view_mode, "3d")

    def test_3d_physics_workspace_switches_projection_without_rebuilding_state(self):
        self.assertTrue(
            self.window._handle_science_request(
                "Simulate 60 particles in a 3D box with elastic collisions."
            )
        )
        self._wait_for_jobs()
        workspace = self.window.chat_list.findChildren(InlinePhysicsWorkspace)[0]
        artifact_identity = id(workspace.canvas.artifact)

        self.assertEqual(workspace.dimension_select.count(), 2)
        workspace.dimension_select.setCurrentText("2D")
        self.assertEqual(workspace.canvas.render_mode, "2d")
        workspace.dimension_select.setCurrentText("3D")
        self.assertEqual(workspace.canvas.render_mode, "3d")
        self.assertEqual(id(workspace.canvas.artifact), artifact_identity)

    def test_orbit_workspace_offers_2d_and_3d_views(self):
        self.assertTrue(
            self.window._handle_science_request("Simulate 8 objects in orbit.")
        )
        self._wait_for_jobs()
        workspace = self.window.chat_list.findChildren(InlinePhysicsWorkspace)[0]
        before = [
            (particle.x, particle.y, particle.z)
            for particle in workspace.canvas.artifact.particles
        ]

        self.assertIsNotNone(workspace.dimension_select)
        workspace.dimension_select.setCurrentText("2D")
        workspace.dimension_select.setCurrentText("3D")
        after = [
            (particle.x, particle.y, particle.z)
            for particle in workspace.canvas.artifact.particles
        ]
        self.assertEqual(before, after)

    def test_elastic_collision_resolves_velocity_along_z_axis(self):
        first = Particle(100, 100, 0, 0, 6, 1, "#fff", z=100, vz=10)
        second = Particle(100, 100, 0, 0, 6, 1, "#fff", z=110, vz=-10)
        instruction = {
            "simulationType": "particle-3d",
            "equations": [],
            "parameters": {"depth": 200, "showVelocityVectors": False},
        }
        artifact = PhysicsArtifact(
            "z collision",
            instruction,
            "particle-3d",
            [first, second],
            gravity=0,
            friction=1,
            restitution=1,
            bounds=(200, 200),
        )
        canvas = PhysicsCanvas()
        canvas.set_artifact(artifact)
        canvas._advance()

        self.assertLess(canvas.artifact.particles[0].vz, 0)
        self.assertGreater(canvas.artifact.particles[1].vz, 0)


if __name__ == "__main__":
    unittest.main()
