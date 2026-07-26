import os
import tempfile
import unittest

from morice.project_builder import (
    ProjectIntentError,
    analyze_project_request,
    build_project_fallback_manifest,
    project_request_contract,
    validate_project_manifest_intent,
)


class ProjectBuilderIntentTests(unittest.TestCase):
    def test_flappy_bird_3d_request_is_understood_as_one_specific_game(self):
        spec = analyze_project_request(
            "Make me a Flappy Bird 3D game in JavaScript with proper physics."
        )

        self.assertEqual(spec.kind, "game")
        self.assertEqual(spec.subject, "flappy bird")
        self.assertEqual(spec.dimension, "3d")
        self.assertEqual(spec.language, "JavaScript")
        self.assertEqual(spec.title, "Flappy Bird 3D")

    def test_contract_makes_language_and_behavior_non_negotiable(self):
        contract = project_request_contract(
            "Build a Flappy Bird 3D game in C++ using OpenGL."
        )

        self.assertIn("Language: C++", contract)
        self.assertIn("Flappy Bird requires flap input", contract)
        self.assertIn("3D must use a real 3D renderer", contract)
        self.assertIn("must not merely become a heading", contract)

    def test_heading_only_or_unrelated_games_are_rejected(self):
        manifest = {
            "files": [
                {
                    "path": "index.html",
                    "content": (
                        "<h1>Make a Flappy Bird 3D game</h1>"
                        "<section>Snake</section><section>Pong</section><section>Memory</section>"
                    ),
                }
            ]
        }

        with self.assertRaises(ProjectIntentError):
            validate_project_manifest_intent(
                manifest,
                "Make me a fully playable Flappy Bird 3D game.",
            )

    def test_explicit_language_cannot_be_silently_replaced(self):
        manifest = {
            "files": [
                {
                    "path": "index.html",
                    "content": "<canvas></canvas><script>requestAnimationFrame(function update(){})</script>",
                }
            ]
        }

        with self.assertRaisesRegex(ProjectIntentError, "requested Python"):
            validate_project_manifest_intent(
                manifest,
                "Build this game in Python with Pygame.",
            )

    def test_language_detection_covers_native_web_mobile_and_scripting_stacks(self):
        cases = {
            "Build the engine in Rust.": "Rust",
            "Create the desktop app in C#.": "C#",
            "Write the service in Go language.": "Go",
            "Make the tool in PowerShell.": "PowerShell",
            "Implement the simulation in Julia.": "Julia",
            "Build the contract in Solidity.": "Solidity",
            "Create the iOS client in SwiftUI.": "Swift",
            "Make the Android client in Kotlin.": "Kotlin",
        }

        for request, expected in cases.items():
            with self.subTest(request=request):
                self.assertEqual(analyze_project_request(request).language, expected)

    def test_framework_detection_does_not_confuse_three_games_with_three_js(self):
        unrelated = analyze_project_request("Build three games for an arcade.")
        react_native = analyze_project_request("Build the mobile app with React Native.")

        self.assertEqual(unrelated.framework, "")
        self.assertEqual(react_native.framework, "React Native")

    def test_flappy_fallback_contains_real_gameplay_and_no_random_game_deck(self):
        request = "Build a polished Flappy Bird 3D game for the browser."
        manifest = build_project_fallback_manifest(request)

        self.assertIsNotNone(manifest)
        validate_project_manifest_intent(manifest, request)
        files = {item["path"]: item["content"] for item in manifest["files"]}
        combined = "\n".join(files.values()).casefold()
        self.assertIn("flappy bird 3d", files["index.html"].casefold())
        self.assertIn("requestanimationframe", files["game.js"].casefold())
        self.assertIn("collision", files["game.js"].casefold())
        self.assertIn("pipe", files["game.js"].casefold())
        self.assertIn("restart", combined)
        self.assertIn("perspective:", files["styles.css"].casefold())
        self.assertNotIn("three mini-games", combined)
        self.assertNotIn("reflex core", combined)

    def test_follow_up_adds_game_without_replacing_existing_site(self):
        with tempfile.TemporaryDirectory() as folder:
            index_path = os.path.join(folder, "index.html")
            original = "<!doctype html><html><body><main>Existing dashboard</main></body></html>"
            with open(index_path, "w", encoding="utf-8") as handle:
                handle.write(original)

            request = "Very good, now add a Flappy Bird 3D game in it too."
            manifest = build_project_fallback_manifest(request, folder)

            self.assertIsNotNone(manifest)
            validate_project_manifest_intent(manifest, request)
            files = {item["path"]: item["content"] for item in manifest["files"]}
            self.assertIn("flappy-bird-3d/index.html", files)
            self.assertIn("Existing dashboard", files["index.html"])
            self.assertIn("data-morice-flappy-bird", files["index.html"])

    def test_unknown_game_never_falls_back_to_unrelated_mini_games(self):
        manifest = build_project_fallback_manifest(
            "Build an original submarine navigation game with sonar."
        )

        self.assertIsNone(manifest)

    def test_unknown_game_subject_cannot_be_satisfied_by_retitled_pong(self):
        request = "Build an original submarine navigation game with sonar."
        fake_loop = (
            "let score = 0; let velocity = 2; "
            "function collision(){ return false; } "
            "function update(){ score += velocity; requestAnimationFrame(update); } "
        ) * 12
        manifest = {
            "files": [
                {
                    "path": "index.html",
                    "content": "<h1>Submarine Navigation Game</h1><canvas></canvas>",
                },
                {"path": "game.js", "content": fake_loop},
            ]
        }

        with self.assertRaisesRegex(ProjectIntentError, "submarine navigation"):
            validate_project_manifest_intent(manifest, request)

    def test_normal_website_fallback_has_no_unsolicited_games(self):
        manifest = build_project_fallback_manifest(
            "Create a responsive portfolio website for a photographer."
        )

        self.assertIsNotNone(manifest)
        combined = "\n".join(item["content"] for item in manifest["files"]).casefold()
        self.assertNotIn("mini-game", combined)
        self.assertNotIn("reflex core", combined)
        self.assertNotIn("star catcher", combined)


if __name__ == "__main__":
    unittest.main()
