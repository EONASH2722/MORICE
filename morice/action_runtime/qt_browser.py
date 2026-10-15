"""Worker-safe bridge over MORICE's existing QWebEngineView, owned by the UI thread."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QThread, QTimer, QUrl, Signal, Slot

from .contracts import UserInterventionRequired


@dataclass
class _Request:
    operation: str
    arguments: dict
    context: object
    done: threading.Event = field(default_factory=threading.Event)
    value: object = None
    error: Exception | None = None


class QtBrowserBridge(QObject):
    requested = Signal(object)

    def __init__(self, view, *, roots=(), parent=None):
        super().__init__(parent or view)
        self.view = view
        self.roots = tuple(Path(p).resolve() for p in roots)
        self._generation = 0
        self._loaded = False
        self._page_loaded = {}
        # Qt deletes its implicit default page on setPage, even after reparenting.
        # Own a normal page in this existing engine when binding an empty view.
        original = view.page()
        self._supports_tabs = original.url().toString() in {"", "about:blank"}
        if self._supports_tabs:
            from PySide6.QtWebEngineCore import QWebEnginePage
            page = self._new_page(original.profile())
            view.setPage(page)
        self._tabs = {"main": view.page()}
        self._tab_id = "main"
        self._download_pending = None
        self._downloads = {}
        self._active_downloads = {}
        self._console_errors = []
        self._download_timer = QTimer(self)
        self._download_timer.setInterval(100)
        self._download_timer.timeout.connect(self._check_downloads)
        self.requested.connect(self._run)
        self._wire(view.page())
        view.page().profile().downloadRequested.connect(self._download)

    def _wire(self, page):
        page.loadStarted.connect(lambda: self._load_start(page))
        page.loadFinished.connect(lambda ok: self._load_finish(page, ok))

    def _new_page(self, profile):
        from PySide6.QtWebEngineCore import QWebEnginePage
        bridge = self
        class ObservedPage(QWebEnginePage):
            def javaScriptConsoleMessage(self, level, message, line, source):
                if level == self.JavaScriptConsoleMessageLevel.ErrorMessageLevel and self is bridge.view.page():
                    bridge._console_errors.append({"level": "error", "line": int(line)})
                    bridge._console_errors[:] = bridge._console_errors[-20:]
        page = ObservedPage(profile, self)
        page._morice_console_observed = True
        return page

    def _load_start(self, page):
        self._page_loaded[page] = False
        if page is self.view.page():
            self._console_errors.clear()
            self._generation += 1
            self._loaded = False

    def _load_finish(self, page, ok):
        self._page_loaded[page] = bool(ok)
        if page is self.view.page():
            self._loaded = bool(ok)

    def _call(self, operation, arguments, context):
        request = _Request(operation, dict(arguments), context)
        if QThread.currentThread() is self.thread():
            raise RuntimeError("Browser action must use an existing background worker.")
        self.requested.emit(request)
        while not request.done.wait(.01):
            context.cancellation_token.raise_if_cancelled()
            if time.monotonic() >= context.deadline:
                raise TimeoutError("Browser request deadline reached.")
        if request.error:
            raise request.error
        return request.value

    def perform(self, verb, target, arguments, context):
        return self._call(verb, {**arguments, "target": target}, context)

    def observe(self, desired, context):
        return self._call("observe", desired, context)

    @staticmethod
    def _element_script(locator):
        # Locator is quoted JSON data. Page text is never interpreted as code.
        return """const loc = %s;
        let all = loc.selector ? Array.from(document.querySelectorAll(loc.selector)) : Array.from(document.querySelectorAll('button,a,input,textarea,select,[role]'));
        all = all.filter(el => {
          const role = el.getAttribute('role') || ({BUTTON:'button', A:'link', INPUT:'textbox', TEXTAREA:'textbox'}[el.tagName] || '');
          const name = el.getAttribute('aria-label') || (el.labels && el.labels[0] && el.labels[0].innerText) || el.innerText || el.getAttribute('placeholder') || '';
          return (!loc.role || role === loc.role) && (!loc.name || name.trim() === loc.name) && (!loc.test_id || el.getAttribute('data-testid') === loc.test_id);
        });
        """ % json.dumps(locator, ensure_ascii=True)

    @Slot(object)
    def _run(self, request):
        try:
            request.context.cancellation_token.raise_if_cancelled()
            if time.monotonic() >= request.context.deadline:
                raise TimeoutError("Expired browser command was withheld.")
            op, args = request.operation, request.arguments
            page = self.view.page()
            if op in {"open", "navigate", "download"}:
                target = args.get("target", "")
                parsed = urlsplit(target)
                if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError("An HTTP(S) URL without credentials is required.")
                if op == "download":
                    destination = Path(args["path"]).expanduser().resolve()
                    if not any(destination.is_relative_to(root) for root in self.roots):
                        raise PermissionError("Download destination is outside approved roots.")
                    if destination.exists() or self._download_pending is not None:
                        raise UserInterventionRequired("Download destination exists or another download is pending.")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    self._download_pending = (target, destination, request.context)
                    self._download_timer.start()
                    page.download(QUrl(target))
                else:
                    self._loaded = False
                    page.setUrl(QUrl(target))
            elif op == "back":
                page.triggerAction(page.WebAction.Back)
            elif op == "forward":
                page.triggerAction(page.WebAction.Forward)
            elif op == "reload":
                self._loaded = False
                page.triggerAction(page.WebAction.Reload)
            elif op == "tab_open":
                if not self._supports_tabs:
                    raise UserInterventionRequired("This view was attached with an existing default page; tab switching needs a new browser session.")
                from PySide6.QtWebEngineCore import QWebEnginePage
                tab_id = str(args.get("tab_id", ""))
                if not tab_id or tab_id in self._tabs or len(self._tabs) >= 8:
                    raise ValueError("A unique tab id is required; at most eight tabs.")
                new_page = self._new_page(page.profile())
                self._tabs[tab_id] = new_page
                self._wire(new_page)
                self.view.setPage(new_page)
                self._tab_id, self._loaded = tab_id, False
                if args.get("target"):
                    new_page.setUrl(QUrl(args["target"]))
            elif op in {"tab_switch", "tab_close"}:
                tab_id = args.get("tab_id", "")
                if tab_id not in self._tabs or op == "tab_close" and len(self._tabs) == 1:
                    raise ValueError("Tab does not exist or is the last tab.")
                if op == "tab_close":
                    old = self._tabs.pop(tab_id)
                    if old is self.view.page():
                        self._tab_id = next(iter(self._tabs))
                        self.view.setPage(self._tabs[self._tab_id])
                    old.deleteLater()
                    self._page_loaded.pop(old, None)
                else:
                    self.view.setPage(self._tabs[tab_id])
                    self._tab_id = tab_id
                self._loaded = self._page_loaded.get(self.view.page(), False)
            elif op in {"click", "type", "submit", "find"}:
                locator = args.get("element", {})
                if not locator or op == "submit" and not args.get("expected_url") and not args.get("expected_text"):
                    raise ValueError("A semantic element and observable expected outcome are required.")
                script = self._element_script(locator)
                if op == "type":
                    script += "if (all.length===1) { const el=all[0]; if(!el.disabled && !el.readOnly){ const setter=Object.getOwnPropertyDescriptor(el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set; setter.call(el,%s); el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); }}" % json.dumps(str(args.get("value", "")))
                elif op in {"click", "submit"}:
                    script += "if(all.length===1 && !all[0].disabled) all[0].click();"
                script += "return {count:all.length};"
                self._javascript(request, "(()=>{" + script + "})()")
                return
            elif op == "inspect":
                destination = Path(args["screenshot_path"]).resolve()
                if not any(destination.is_relative_to(root) for root in self.roots):
                    raise PermissionError("Screenshot path is outside approved roots.")
                if not self.view.isVisible():
                    raise UserInterventionRequired("Open the browser panel for actual rendered inspection.")
                locators = args.get("regions", [])
                if len(locators) > 20:
                    raise ValueError("At most twenty inspected regions.")
                viewport = args.get("viewport", ())
                previous_size = self.view.size()
                previous_min, previous_max = self.view.minimumSize(), self.view.maximumSize()
                if viewport:
                    width, height = (int(v) for v in viewport)
                    if not 240 <= width <= 2560 or not 240 <= height <= 1440:
                        raise ValueError("Inspection viewport is outside supported bounds.")
                    self.view.setFixedSize(width, height)
                script = "const locators=" + json.dumps(locators) + "; const regions=locators.map(loc=>{ const all=Array.from(document.querySelectorAll(loc.selector)); if(all.length!==1)return {selector:loc.selector,count:all.length}; const el=all[0],r=el.getBoundingClientRect(),s=getComputedStyle(el); return {selector:loc.selector,count:1,x:r.x,y:r.y,width:r.width,height:r.height,visible:s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0,text:el.innerText.slice(0,500),font_size:parseFloat(s.fontSize),color:s.color,background:s.backgroundColor}; }); return {url:location.href,ready:document.readyState,viewport:[innerWidth,innerHeight],scroll_width:document.documentElement.scrollWidth,regions:regions};"
                generation = self._generation
                def capture(value):
                    try:
                        if request.context.cancellation_token.cancelled or time.monotonic() >= request.context.deadline or generation != self._generation or page is not self.view.page():
                            raise TimeoutError("Expired rendered inspection was ignored.")
                        state = json.loads(value) if isinstance(value, str) else value
                        if not isinstance(state, dict):
                            raise RuntimeError("Rendered layout facts are unavailable.")
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        if not self.view.grab().save(str(destination), "PNG"):
                            raise RuntimeError("Actual browser screenshot could not be saved.")
                        request.value = {**state, "loaded": self._loaded and state.get("ready") == "complete",
                            "screenshot_path": str(destination), "console_errors": list(self._console_errors), "console_available": bool(getattr(page, "_morice_console_observed", False)),
                            "timestamp": time.time()}
                    except Exception as exc:
                        request.error = exc
                    finally:
                        if viewport:
                            self.view.setMinimumSize(previous_min)
                            self.view.setMaximumSize(previous_max)
                            self.view.resize(previous_size)
                        request.done.set()
                def inspect_layout():
                    if request.context.cancellation_token.cancelled or time.monotonic() >= request.context.deadline:
                        if viewport:
                            self.view.setMinimumSize(previous_min)
                            self.view.setMaximumSize(previous_max)
                            self.view.resize(previous_size)
                        request.error = TimeoutError("Inspection cancelled before DOM access."); request.done.set(); return
                    page.runJavaScript("JSON.stringify((()=>{" + script + "})())", capture)
                QTimer.singleShot(80, inspect_layout)
                return
            elif op in {"observe", "extract"}:
                element = args.get("element", {})
                script = self._element_script(element) if element else "const all=[];"
                script += """const text=(document.body ? document.body.innerText : '').slice(0,16000);
                const el=all.length===1?all[0]:null;
                return {url:location.href,title:document.title,text:text,ready:document.readyState,
                  element:{count:all.length,value:el && el.value !== undefined ? el.value : null},
                  waiting_for_user:!!document.querySelector('input[type=password],iframe[src*="recaptcha"],iframe[src*="hcaptcha"],input[autocomplete="one-time-code"]')};"""
                self._javascript(request, "(()=>{" + script + "})()", observing=True)
                return
            elif op == "upload":
                raise UserInterventionRequired("File upload needs a document-associated file-picker adapter; user selection is required.")
            else:
                raise ValueError("Unsupported browser operation.")
            request.value = {"attempted": True, "tab_id": self._tab_id}
        except Exception as exc:
            request.error = exc
        request.done.set()

    def _javascript(self, request, script, *, observing=False):
        page = self.view.page()
        generation = self._generation
        def finished(value):
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except ValueError:
                    value = None
            if request.context.cancellation_token.cancelled or time.monotonic() >= request.context.deadline:
                request.error = TimeoutError("Late browser observation ignored.")
            elif page is not self.view.page() or generation != self._generation:
                request.error = RuntimeError("Page changed during observation.")
            elif not isinstance(value, dict):
                request.error = RuntimeError(f"Browser DOM is unavailable ({type(value).__name__}).")
            else:
                request.value = {**value, "available": True, "loaded": self._loaded and value.get("ready") == "complete",
                    "generation": generation, "tab_id": self._tab_id, "tabs": list(self._tabs),
                    "downloads": dict(self._downloads), "timestamp": time.time()} if observing else value
            request.done.set()
        page.runJavaScript("JSON.stringify(" + script + ")", finished)

    @Slot(object)
    def _download(self, download):
        if download.page() not in self._tabs.values():
            return  # Other MORICE windows share the default browser profile.
        pending = self._download_pending
        if pending is None or download.url().toString() != pending[0]:
            download.cancel()
            return
        target, path, context = pending
        self._download_pending = None
        if context.cancellation_token.cancelled or time.monotonic() >= context.deadline:
            download.cancel()
            return
        download.setDownloadDirectory(str(path.parent))
        download.setDownloadFileName(path.name)
        self._downloads[str(path)] = {"completed": False, "url": target}
        self._active_downloads[download] = context
        def changed(*unused):
            if context.cancellation_token.cancelled:
                download.cancel()
            complete = download.state() == download.DownloadState.DownloadCompleted
            self._downloads[str(path)] = {"completed": complete, "url": target,
                "received": int(download.receivedBytes()), "total": int(download.totalBytes())}
            if download.isFinished():
                self._active_downloads.pop(download, None)
        download.stateChanged.connect(changed)
        download.receivedBytesChanged.connect(changed)
        download.accept()

    def cancel_downloads(self):
        self._download_pending = None
        for download in tuple(self._active_downloads):
            download.cancel()
        self._active_downloads.clear()
        self._download_timer.stop()

    def _check_downloads(self):
        if self._download_pending is not None:
            context = self._download_pending[2]
            if context.cancellation_token.cancelled or time.monotonic() >= context.deadline:
                self._download_pending = None
        for download, context in tuple(self._active_downloads.items()):
            if context.cancellation_token.cancelled or time.monotonic() >= context.deadline:
                download.cancel()
                self._active_downloads.pop(download, None)
        if self._download_pending is None and not self._active_downloads:
            self._download_timer.stop()
