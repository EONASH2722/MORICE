from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from morice.desktop_environment import (
    ApplicationCandidate,
    ApplicationManager,
    DesktopPermissionManager,
)
from morice.media_control import AMAZON_MUSIC_APP_ID, WindowsMediaSessionBackend


class ApplicationDiscoveryTests(unittest.TestCase):
    def test_persisted_application_index_serves_first_resolution_without_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "applications.json"
            state_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "pinned": [],
                        "recent": [],
                        "discoveryCachedAt": time.time(),
                        "discovery": [
                            {
                                "name": "Calculator",
                                "target": "calc.exe",
                                "source": "path",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            manager = ApplicationManager(
                Path(directory),
                DesktopPermissionManager(),
            )
            with patch.object(
                manager,
                "_build_discovery_cache",
                side_effect=AssertionError("persistent cache should be hot"),
            ):
                resolved = manager.resolve("Calculator")

            self.assertIsNotNone(resolved)
            self.assertEqual("calc.exe", resolved.target)

    def test_store_app_and_generic_music_alias_resolve_from_cached_index(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = ApplicationManager(
                Path(directory),
                DesktopPermissionManager(),
                default_music_provider="Amazon Music",
            )
            amazon = ApplicationCandidate(
                "Amazon Music",
                AMAZON_MUSIC_APP_ID,
                "start-app",
            )
            with (
                patch.object(manager, "_shortcut_roots", return_value=()),
                patch.object(manager, "_start_apps", return_value=[amazon]),
                patch.object(manager, "_registry_app_paths", return_value=[]),
                patch.object(manager, "_path_applications", return_value=[]),
                patch.object(manager, "_common_location_applications", return_value=[]),
                patch.object(manager, "list_processes", return_value=[]),
            ):
                manager.refresh_discovery(force=True)

            direct = manager.resolve("amazon music")
            generic = manager.resolve("music app")

            self.assertEqual(direct, amazon)
            self.assertEqual(generic, amazon)
            self.assertEqual(manager.refresh_discovery(), (amazon,))

    def test_default_provider_is_runtime_configurable(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = ApplicationManager(
                Path(directory),
                DesktopPermissionManager(),
                default_music_provider="Amazon Music",
            )
            spotify = ApplicationCandidate("Spotify", "Spotify.App", "start-app")
            manager._discovery_cache = (spotify,)
            manager._discovery_cached_at = 10**12

            manager.set_default_music_provider("Spotify")

            self.assertEqual(manager.resolve("music"), spotify)

    def test_browser_alias_never_selects_internal_browser_broker(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = ApplicationManager(
                Path(directory),
                DesktopPermissionManager(),
            )
            preferred = ApplicationCandidate(
                "Brave",
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                "default-browser",
            )
            with (
                patch.object(
                    manager,
                    "_default_browser_candidate",
                    return_value=preferred,
                ),
                patch.object(
                    manager,
                    "refresh_discovery",
                    return_value=(
                        ApplicationCandidate(
                            "browser_broker",
                            r"C:\Windows\System32\browser_broker.exe",
                            "path",
                        ),
                    ),
                ),
            ):
                resolved = manager.resolve("browser")

            self.assertEqual(resolved, preferred)


class NativeMediaSessionTests(unittest.TestCase):
    def test_provider_matching_accepts_amazon_store_identity(self):
        self.assertTrue(
            WindowsMediaSessionBackend._matches_provider(
                AMAZON_MUSIC_APP_ID,
                "Amazon Music",
            )
        )
        self.assertFalse(
            WindowsMediaSessionBackend._matches_provider(
                AMAZON_MUSIC_APP_ID,
                "Spotify",
            )
        )


if __name__ == "__main__":
    unittest.main()
