from __future__ import annotations

"""Explicit, isolated WebEngine QObject ownership scenario for Doctor.

Not part of Dofus Atlas startup. Never navigates a URL, uses the user's
browser/profile or reads application data. Running this may start Chromium;
invoke manually only for final validation on a suitable machine.
"""
from tools.atlas_doctor_lib.runtime_observation import active_observer


def main() -> None:
    observer = active_observer()
    if observer is None:
        raise RuntimeError("Run only by explicit Doctor runtime-trace or capture-ui")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from shiboken6 import delete, isValid

    application = QApplication.instance() or QApplication([])
    view = QWebEngineView()
    # Unnamed profile is off-the-record: no persistent user profile/cache.
    profile = QWebEngineProfile(view)
    page = QWebEnginePage(profile, view)
    view.setPage(page)
    for obj, name in ((view, "webengine-view"), (page, "webengine-page"),
                      (profile, "webengine-profile")):
        if not observer.watch(obj, label=name, kind="qobject"):
            raise AssertionError("Cannot register WebEngine weak lifecycle watch")
        if not observer.watch_qt_destroyed(obj, label=name):
            raise AssertionError("Cannot register QObject destroyed signal")
    if page.parent() is not view or profile.parent() is not view:
        raise AssertionError("Explicit WebEngine Qt parent relation not established")
    observer.snapshot_watches(label="webengine-created")
    observer.snapshot_qt_objects(label="webengine-created")
    observer.snapshot_process_tree(label="webengine-created")
    # Never call .show(), .load(), .setUrl() or process event loop here.
    # Native parent ownership does not prove Chromium process cleanup.
    delete(view)
    if any(isValid(obj) for obj in (view, page, profile)):
        raise AssertionError("Explicit WebEngine native children remained valid")
    observer.snapshot_watches(label="webengine-destroyed")
    observer.snapshot_qt_objects(label="webengine-destroyed")
    observer.snapshot_process_tree(label="webengine-destroyed")
    if application is None:
        raise AssertionError("QApplication unavailable")


if __name__ == "__main__":
    main()
