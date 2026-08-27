from __future__ import annotations

import asyncio
import ctypes
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable


AMAZON_MUSIC_APP_ID = (
    "AmazonMobileLLC.AmazonMusic_kc6t79cpj4tp0!"
    "AmazonMobileLLC.AmazonMusic"
)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split()).strip()


def _provider_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean(value).casefold())


def _run_async(awaitable):
    """Run one WinRT async operation from MORICE's worker threads."""

    return asyncio.run(awaitable)


@dataclass(frozen=True)
class MediaSelection:
    source_app_id: str
    title: str = ""
    artist: str = ""
    album: str = ""
    playback_state: str = "unknown"


class WindowsMediaSessionBackend:
    """Native Windows GSMTC transport and metadata bridge.

    Imports stay lazy so MORICE still launches with a clear degraded capability
    when the optional WinRT wheels are not available.
    """

    STATUS_NAMES = {
        0: "closed",
        1: "opened",
        2: "changing",
        3: "stopped",
        4: "playing",
        5: "paused",
    }

    @staticmethod
    def available() -> bool:
        if os.name != "nt":
            return False
        try:
            from winrt.windows.media.control import (  # noqa: F401
                GlobalSystemMediaTransportControlsSessionManager,
            )
        except (ImportError, OSError):
            return False
        return True

    @staticmethod
    def _matches_provider(source_app_id: str, provider: str) -> bool:
        requested = _provider_key(provider)
        if not requested or requested in {"activemedia", "systemaudio"}:
            return True
        source = _provider_key(source_app_id)
        aliases = {
            "amazonmusic": ("amazonmusic", "amazonmobilellc"),
            "spotify": ("spotify",),
            "youtubemusic": ("youtubemusic", "youtube"),
        }
        tokens = aliases.get(requested, (requested,))
        return any(token in source for token in tokens)

    async def _manager(self):
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager,
        )

        return await GlobalSystemMediaTransportControlsSessionManager.request_async()

    def _select(self, manager: Any, provider: str = "") -> Any | None:
        sessions = list(manager.get_sessions())
        if provider:
            for session in sessions:
                if self._matches_provider(session.source_app_user_model_id, provider):
                    return session
        current = manager.get_current_session()
        return current or (sessions[0] if sessions else None)

    async def _status_async(
        self,
        provider: str = "",
        *,
        include_metadata: bool = True,
    ) -> dict[str, Any]:
        manager = await self._manager()
        session = self._select(manager, provider)
        if session is None:
            return {
                "available": True,
                "sessionAvailable": False,
                "provider": provider,
                "playbackState": "unavailable",
                "currentTrack": None,
            }
        source = _clean(session.source_app_user_model_id)
        info = session.get_playback_info()
        raw_status = int(info.playback_status)
        timeline = session.get_timeline_properties()
        if include_metadata:
            try:
                properties = await asyncio.wait_for(
                    session.try_get_media_properties_async(),
                    timeout=0.6,
                )
                title = _clean(properties.title)
                artist = _clean(properties.artist)
                album = _clean(properties.album_title)
            except Exception:  # noqa: BLE001 - metadata is optional per session
                title = artist = album = ""
        else:
            title = artist = album = ""
        controls = getattr(info, "controls", None)
        capability_names = (
            "is_play_enabled",
            "is_pause_enabled",
            "is_next_enabled",
            "is_previous_enabled",
            "is_playback_position_enabled",
        )
        capabilities = {
            name.removeprefix("is_").removesuffix("_enabled"): bool(
                getattr(controls, name, False)
            )
            for name in capability_names
        }
        return {
            "available": True,
            "sessionAvailable": True,
            "sourceAppId": source,
            "provider": provider or source,
            "playbackState": self.STATUS_NAMES.get(raw_status, str(raw_status)),
            "currentTrack": title or None,
            "artist": artist or None,
            "album": album or None,
            "playbackPosition": max(0.0, timeline.position.total_seconds()),
            "duration": max(0.0, timeline.end_time.total_seconds()),
            "capabilities": capabilities,
        }

    def status(
        self,
        provider: str = "",
        *,
        include_metadata: bool = True,
    ) -> dict[str, Any]:
        if not self.available():
            return {
                "available": False,
                "sessionAvailable": False,
                "provider": provider,
                "playbackState": "unavailable",
                "currentTrack": None,
                "reason": "Windows media-session support is not installed.",
            }
        try:
            return dict(
                _run_async(
                    self._status_async(
                        provider,
                        include_metadata=include_metadata,
                    )
                )
            )
        except Exception as exc:  # noqa: BLE001 - expose a clean degraded status
            return {
                "available": False,
                "sessionAvailable": False,
                "provider": provider,
                "playbackState": "unavailable",
                "currentTrack": None,
                "reason": f"Windows media-session query failed: {exc}",
            }

    async def _control_async(self, action: str, provider: str = "") -> bool:
        manager = await self._manager()
        session = self._select(manager, provider)
        if session is None:
            return False
        operations = {
            "pause": session.try_pause_async,
            "resume": session.try_play_async,
            "play": session.try_play_async,
            "next": session.try_skip_next_async,
            "previous": session.try_skip_previous_async,
        }
        if action == "restart":
            return bool(await session.try_change_playback_position_async(0))
        operation = operations.get(action)
        if operation is None:
            return False
        return bool(await operation())

    def control(self, action: str, provider: str = "") -> bool:
        if not self.available():
            return False
        try:
            return bool(_run_async(self._control_async(action, provider)))
        except Exception:
            return False


class SystemVolumeBackend:
    """Verified Windows endpoint-volume control using the default output device."""

    @staticmethod
    def _endpoint():
        from pycaw.pycaw import AudioUtilities

        return AudioUtilities.GetSpeakers().EndpointVolume

    def status(self) -> dict[str, Any]:
        if os.name != "nt":
            return {"available": False, "volume": None, "muted": None}
        try:
            endpoint = self._endpoint()
            return {
                "available": True,
                "volume": round(float(endpoint.GetMasterVolumeLevelScalar()) * 100.0, 1),
                "muted": bool(endpoint.GetMute()),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "available": False,
                "volume": None,
                "muted": None,
                "reason": f"Windows volume query failed: {exc}",
            }

    def set_percent(self, percent: float) -> dict[str, Any]:
        endpoint = self._endpoint()
        bounded = max(0.0, min(100.0, float(percent)))
        endpoint.SetMasterVolumeLevelScalar(bounded / 100.0, None)
        return self.status()

    def adjust(self, delta_percent: float) -> dict[str, Any]:
        before = self.status()
        current = float(before.get("volume") or 0.0)
        return self.set_percent(current + float(delta_percent))

    def toggle_mute(self) -> dict[str, Any]:
        endpoint = self._endpoint()
        endpoint.SetMute(not bool(endpoint.GetMute()), None)
        return self.status()


class AmazonMusicController:
    """Amazon Music search/play automation based on Windows accessibility.

    No coordinates or display-size assumptions are used. Controls are resolved
    by window name, AutomationId, control type, semantic labels, and tree order.
    """

    WINDOW_NAME = "Amazon Music"

    @staticmethod
    def available() -> bool:
        if os.name != "nt":
            return False
        try:
            import uiautomation  # noqa: F401
        except (ImportError, OSError):
            return False
        return True

    @staticmethod
    def _walk(control: Any, *, depth: int = 10) -> list[tuple[Any, int]]:
        import uiautomation as auto

        return list(auto.WalkControl(control, includeTop=False, maxDepth=depth))

    @staticmethod
    def _invoke(control: Any) -> None:
        try:
            control.GetInvokePattern().Invoke()
        except Exception:
            control.Click(simulateMove=False)

    @staticmethod
    def _activate_window(window: Any) -> bool:
        if os.name != "nt":
            return False
        handle = int(getattr(window, "NativeWindowHandle", 0) or 0)
        if not handle:
            return False
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        foreground = int(user32.GetForegroundWindow() or 0)
        current_thread = int(kernel32.GetCurrentThreadId())
        foreground_thread = int(
            user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        )
        target_thread = int(user32.GetWindowThreadProcessId(handle, None))
        attached: list[int] = []
        try:
            for thread_id in dict.fromkeys((foreground_thread, target_thread)):
                if thread_id and thread_id != current_thread:
                    if user32.AttachThreadInput(current_thread, thread_id, True):
                        attached.append(thread_id)
            user32.ShowWindow(handle, 9)  # SW_RESTORE
            user32.BringWindowToTop(handle)
            user32.SetForegroundWindow(handle)
            user32.SetActiveWindow(handle)
            return int(user32.GetForegroundWindow() or 0) == handle
        finally:
            for thread_id in reversed(attached):
                user32.AttachThreadInput(current_thread, thread_id, False)

    def _window(self, timeout: float = 10.0):
        import uiautomation as auto

        window = auto.WindowControl(searchDepth=2, Name=self.WINDOW_NAME)
        if not window.Exists(max(0.1, timeout), 0.25):
            raise RuntimeError("Amazon Music did not expose a visible window.")
        return window

    @staticmethod
    def _control_names(control: Any) -> list[str]:
        names: list[str] = []
        for child, _depth in AmazonMusicController._walk(control, depth=8):
            name = _clean(getattr(child, "Name", ""))
            if name:
                names.append(name)
        return names

    def now_playing(self) -> dict[str, Any]:
        if not self.available():
            return {"available": False, "reason": "Amazon accessibility support is unavailable."}
        try:
            window = self._window(1.0)
            transport = window.Control(
                searchDepth=14,
                AutomationId="transportContainer",
            )
            if not transport.Exists(0.5, 0.1):
                return {"available": True, "visible": False}
            title_control = transport.HyperlinkControl(searchDepth=8, foundIndex=1)
            current_track = (
                _clean(title_control.Name)
                if title_control.Exists(0.5, 0.05)
                else ""
            )
            native = WindowsMediaSessionBackend().status(self.WINDOW_NAME)
            artist = _clean(native.get("artist"))
            names = [item for item in (current_track, artist) if item]
            return {
                "available": True,
                "visible": True,
                "labels": names[:40],
                "currentTrack": current_track or None,
                "artist": artist or None,
            }
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "visible": False, "reason": str(exc)}

    def play(self, query: str, *, timeout: float = 22.0) -> dict[str, Any]:
        started = time.perf_counter()
        timings_ms: dict[str, float] = {}

        def mark(name: str) -> None:
            timings_ms[name] = round((time.perf_counter() - started) * 1_000, 1)

        if not self.available():
            raise RuntimeError("Amazon Music accessibility control is not installed.")
        import uiautomation as auto

        clean_query = _clean(query)
        if not clean_query:
            raise ValueError("Tell me which song, artist, album, or playlist to play.")
        window = self._window(timeout=min(timeout, 10.0))
        mark("windowReady")
        search = window.EditControl(searchDepth=14, Name="Search")
        if not search.Exists(0.7, 0.05):
            existing_continue = window.ButtonControl(
                searchDepth=14,
                Name="Continue",
            )
            if existing_continue.Exists(0.7, 0.05):
                self._invoke(existing_continue)
                time.sleep(0.25)
                search = window.EditControl(searchDepth=14, Name="Search")
            if not search.Exists(1.5, 0.1):
                raise RuntimeError("Amazon Music's Search control was not found.")
        mark("searchReady")
        self._activate_window(window)
        search.Click(simulateMove=False, waitTime=0.05)
        search.SetFocus()
        auto.SendKeys("{Ctrl}a", waitTime=0.05)
        auto.SendKeys(clean_query, interval=0.01, waitTime=0.05)
        auto.SendKeys("{Enter}", waitTime=0.2)
        mark("searchSubmitted")

        deadline = time.monotonic() + timeout
        selected_title = ""
        selected_artist = ""
        play_button = None
        main = window.Control(searchDepth=14, AutomationId="main-content")
        if not main.Exists(2.0, 0.1):
            raise RuntimeError("Amazon Music's search results panel was not found.")
        marker = main.TextControl(
            searchDepth=8,
            RegexName=r"Showing results for.*",
        )
        normalized_query = re.sub(
            r"[^a-z0-9]+", " ", clean_query.casefold()
        ).strip()
        query_words = [word for word in normalized_query.split() if len(word) > 1]
        while time.monotonic() < deadline:
            if marker.Exists(0.25, 0.05):
                marker_text = _clean(marker.Name).casefold()
                if all(word in marker_text for word in query_words):
                    break
            time.sleep(0.1)
        else:
            raise RuntimeError(
                f"Amazon Music did not finish searching for {clean_query!r}."
            )
        mark("resultsReady")

        title_control = main.HyperlinkControl(searchDepth=8, foundIndex=1)
        title_deadline = time.monotonic() + 5.0
        while time.monotonic() < title_deadline:
            if title_control.Exists(0.3, 0.05) and _clean(title_control.Name):
                break
            time.sleep(0.1)
            title_control = main.HyperlinkControl(searchDepth=8, foundIndex=1)
        if not title_control.Exists(0.2, 0.05) or not _clean(title_control.Name):
            raise RuntimeError(
                f"Amazon Music returned no playable song result for {clean_query!r}."
            )
        selected_title = _clean(title_control.Name)
        container = title_control
        for _level in range(6):
            container = container.GetParentControl()
            if container is None:
                break
            controls = self._walk(container, depth=6)
            title_index = next(
                (
                    index
                    for index, (control, _depth) in enumerate(controls)
                    if getattr(control, "ControlTypeName", "") == "HyperlinkControl"
                    and _clean(getattr(control, "Name", "")) == selected_title
                ),
                -1,
            )
            if title_index < 0:
                continue
            selected_artist = next(
                (
                    _clean(control.Name)
                    for control, _depth in controls[title_index + 1 : title_index + 8]
                    if getattr(control, "ControlTypeName", "") == "TextControl"
                    and _clean(getattr(control, "Name", ""))
                ),
                "",
            )
            play_button = next(
                (
                    control
                    for control, _depth in reversed(controls[:title_index])
                    if getattr(control, "ControlTypeName", "") == "ButtonControl"
                ),
                None,
            )
            if play_button is not None:
                break
        if play_button is None:
            raise RuntimeError(
                f"Amazon Music returned no playable song result for {clean_query!r}."
            )
        mark("resultResolved")

        self._invoke(play_button)
        mark("playInvoked")

        verified = False
        now_playing: dict[str, Any] = {}
        session_status: dict[str, Any] = {}
        sessions = WindowsMediaSessionBackend()
        quick_deadline = time.monotonic() + 1.2
        selected_key = selected_title.casefold()
        while time.monotonic() < quick_deadline:
            session_status = sessions.status(self.WINDOW_NAME)
            session_title = _clean(session_status.get("currentTrack")).casefold()
            if selected_key and (
                selected_key in session_title or session_title in selected_key
            ):
                break
            time.sleep(0.1)
        else:
            # Amazon may ask whether playback should move from another signed-in
            # device. Resolve that semantic dialog only when the requested track
            # did not start, avoiding a full-tree scan on normal requests.
            continue_button = window.ButtonControl(
                searchDepth=14,
                Name="Continue",
            )
            if continue_button.Exists(0.7, 0.05):
                self._invoke(continue_button)
        mark("streamConfirmed")
        verification_deadline = time.monotonic() + min(timeout, 10.0)
        while time.monotonic() < verification_deadline:
            session_status = sessions.status(self.WINDOW_NAME)
            session_title = _clean(session_status.get("currentTrack")).casefold()
            if (
                session_status.get("playbackState") == "playing"
                and selected_key
                and (selected_key in session_title or session_title in selected_key)
            ):
                verified = True
                break
            time.sleep(0.15)
        mark("sessionVerified")
        now_playing = {
            "available": bool(session_status.get("sessionAvailable")),
            "visible": True,
            "currentTrack": session_status.get("currentTrack"),
            "artist": session_status.get("artist"),
            "source": "Windows GSMTC",
        }
        # The UI result was selected semantically and the native Amazon media
        # session independently reports that exact track as playing.
        verified = bool(verified)
        mark("uiVerified")
        timings_ms["total"] = timings_ms["uiVerified"]
        return {
            "provider": self.WINDOW_NAME,
            "requestedQuery": clean_query,
            "selectedTitle": selected_title,
            "selectedArtist": selected_artist,
            "uiVerified": verified,
            "nowPlaying": now_playing,
            "session": session_status,
            "timingsMs": timings_ms,
        }


__all__ = [
    "AMAZON_MUSIC_APP_ID",
    "AmazonMusicController",
    "MediaSelection",
    "SystemVolumeBackend",
    "WindowsMediaSessionBackend",
]
