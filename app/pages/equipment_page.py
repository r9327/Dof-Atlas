from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.constants import HUZOUNET_URL


QWebEngineView = None
QWebEnginePage = None
_QWEBENGINE_IMPORT_ATTEMPTED = False
_RESTRICTED_PAGE_CLASS = None
WEBENGINE_START_DELAY_MS = 60


def qwebengine_view_class():
    global QWebEngineView, QWebEnginePage, _QWEBENGINE_IMPORT_ATTEMPTED
    if not _QWEBENGINE_IMPORT_ATTEMPTED:
        _QWEBENGINE_IMPORT_ATTEMPTED = True
        try:
            from PySide6.QtWebEngineCore import QWebEnginePage as imported_page
            from PySide6.QtWebEngineWidgets import QWebEngineView as imported_view
        except Exception:
            imported_view = None
            imported_page = None
        QWebEngineView = imported_view
        QWebEnginePage = imported_page
    return QWebEngineView


def restricted_equipment_page_class():
    global _RESTRICTED_PAGE_CLASS
    if _RESTRICTED_PAGE_CLASS is not None:
        return _RESTRICTED_PAGE_CLASS
    if qwebengine_view_class() is None or QWebEnginePage is None:
        return None

    class RestrictedEquipmentPage(QWebEnginePage):
        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self.allowed_host = QUrl(HUZOUNET_URL).host().casefold()

        def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
            if not is_main_frame:
                return super().acceptNavigationRequest(url, navigation_type, is_main_frame)

            scheme = str(url.scheme() or "").casefold()
            host = str(url.host() or "").casefold()
            if scheme in {"about", "data", "blob"}:
                return True
            if scheme in {"http", "https"} and (
                host == self.allowed_host
                or (self.allowed_host and host.endswith("." + self.allowed_host))
            ):
                return super().acceptNavigationRequest(url, navigation_type, is_main_frame)

            if navigation_type == QWebEnginePage.NavigationTypeLinkClicked:
                QDesktopServices.openUrl(url)
            return False

    _RESTRICTED_PAGE_CLASS = RestrictedEquipmentPage
    return _RESTRICTED_PAGE_CLASS


class EquipmentPage(QWidget):
    def __init__(self, status_callback, parent: QWidget | None = None):
        super().__init__(parent)
        self.status_callback = status_callback
        self.web_loaded = False
        self.web_unavailable = False
        self._web_start_scheduled = False
        self.ready_callbacks: list[Callable[[], None]] = []
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(8, 6, 8, 8)
        self.root_layout.setSpacing(6)
        title = QLabel("Équipement")
        title.setObjectName("PageTitle")
        self.root_layout.addWidget(title)
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self.fit_web_content)
        self.placeholder = QLabel("Préparation...")
        self.placeholder.setObjectName("CompactLabel")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.root_layout.addWidget(self.placeholder, 1)

    def is_navigation_ready(self) -> bool:
        """The lightweight shell is immediately navigable.

        QtWebEngine import and Chromium creation can be noticeably expensive on
        Windows. Navigation must never wait for that work: paint the Equipment
        placeholder first, then start the browser after the event loop gets a
        chance to render the new page.
        """

        return True

    def prepare_for_navigation(self, ready_callback: Callable[[], None] | None = None) -> bool:
        if ready_callback is not None:
            QTimer.singleShot(0, ready_callback)
        self.schedule_web_start()
        return True

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.schedule_web_start()

    def schedule_web_start(self) -> None:
        if self.web_loaded or self.web_unavailable or self._web_start_scheduled:
            return
        self._web_start_scheduled = True
        QTimer.singleShot(WEBENGINE_START_DELAY_MS, self._start_scheduled_web)

    def _start_scheduled_web(self) -> None:
        self._web_start_scheduled = False
        if not self.isVisible() or self.web_loaded or self.web_unavailable:
            return
        self.ensure_web_loaded()

    def ensure_web_loaded(self) -> None:
        self._web_start_scheduled = False
        if self.web_loaded or self.web_unavailable:
            return
        view_class = qwebengine_view_class()
        page_class = restricted_equipment_page_class()
        if view_class is None or page_class is None:
            self.web_unavailable = True
            if hasattr(self, "placeholder"):
                self.root_layout.removeWidget(self.placeholder)
                self.placeholder.deleteLater()
            warning = QLabel("QWebEngineView indisponible : Huzounet ne peut pas être intégré.")
            warning.setObjectName("WarningLabel")
            warning.setWordWrap(True)
            self.root_layout.addWidget(warning)
            self.root_layout.addStretch(1)
            self.emit_navigation_ready()
            return
        self.web_loaded = True
        if hasattr(self, "placeholder"):
            self.root_layout.removeWidget(self.placeholder)
            self.placeholder.deleteLater()
        self.web = view_class()
        self.web.setPage(page_class(self.web))
        self.web.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.web.setZoomFactor(1.0)
        self.web.loadFinished.connect(self.on_web_loaded)
        self.root_layout.addWidget(self.web, 1)
        self.web.load(QUrl(HUZOUNET_URL))
        self.emit_navigation_ready()
        self.status_callback("Équipement ouvert.")

    def emit_navigation_ready(self) -> None:
        callbacks = list(self.ready_callbacks)
        self.ready_callbacks.clear()
        for callback in callbacks:
            callback()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.schedule_web_fit()

    def on_web_loaded(self, ok: bool = True) -> None:
        if not ok or not hasattr(self, "web"):
            return
        self.web.setZoomFactor(1.0)
        self.schedule_web_fit(50)

    def schedule_web_fit(self, delay_ms: int = 120) -> None:
        if hasattr(self, "fit_timer"):
            self.fit_timer.start(delay_ms)

    def fit_web_content(self) -> None:
        if not hasattr(self, "web"):
            return
        self.web.setZoomFactor(1.0)
        script = """
(() => {
  const styleId = "atlas-fit-equipment-scrollbars";
  let style = document.getElementById(styleId);
  if (!style) {
    style = document.createElement("style");
    style.id = styleId;
    (document.head || document.documentElement).appendChild(style);
  }
  style.textContent = `
    html, body {
      scrollbar-width: none !important;
      -ms-overflow-style: none !important;
    }
    html::-webkit-scrollbar,
    body::-webkit-scrollbar,
    *::-webkit-scrollbar {
      width: 0 !important;
      height: 0 !important;
      display: none !important;
      background: transparent !important;
    }
  `;
  const html = document.documentElement;
  const body = document.body;
  if (!body) {
    return 1;
  }
  html.style.overflow = "";
  body.style.overflow = "";
  body.style.transform = "";
  body.style.transformOrigin = "";
  body.style.width = "";
  body.style.minHeight = "";
  body.style.zoom = "";
  return 1;
})();
"""
        self.web.page().runJavaScript(script)