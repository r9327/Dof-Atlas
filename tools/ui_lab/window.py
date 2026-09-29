from __future__ import annotations

import traceback
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tools.ui_lab.registry import PreviewSpec, default_previews, resolve_factory
from tools.ui_lab.screens import PreviewContext


class UiLabWindow(QMainWindow):
    """Standalone developer window that hosts real Dofus Atlas widgets."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Dofus Atlas — UI Lab")
        self.resize(1500, 900)

        self._sandbox = TemporaryDirectory(prefix="dofus_atlas_ui_lab_")
        self._specs = {spec.key: spec for spec in default_previews()}
        self._current_spec: PreviewSpec | None = None
        self._current_preview: QWidget | None = None

        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        title = QLabel("UI Lab — vues réelles Dofus Atlas")
        title.setObjectName("PageTitle")
        root_layout.addWidget(title)

        subtitle = QLabel(
            "Catalogue développeur isolé : les écrans branchés utilisent le vrai code produit, "
            "avec des fichiers de progression temporaires quand nécessaire."
        )
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        root_layout.addWidget(subtitle)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root_layout.addWidget(splitter, 1)

        self.catalog = QTreeWidget()
        self.catalog.setHeaderHidden(True)
        self.catalog.setMinimumWidth(230)
        self.catalog.setMaximumWidth(320)
        self.catalog.currentItemChanged.connect(self._on_current_item_changed)
        splitter.addWidget(self.catalog)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(8)

        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        text_column = QVBoxLayout()
        text_column.setSpacing(2)
        self.preview_title = QLabel("Sélectionne une vue")
        self.preview_title.setObjectName("PageTitle")
        self.preview_meta = QLabel("")
        self.preview_meta.setObjectName("MutedLabel")
        self.preview_meta.setWordWrap(True)
        text_column.addWidget(self.preview_title)
        text_column.addWidget(self.preview_meta)
        header_layout.addLayout(text_column, 1)

        self.reload_button = QPushButton("Recharger")
        self.reload_button.clicked.connect(self._reload_current)
        self.reload_button.setEnabled(False)
        header_layout.addWidget(self.reload_button)

        self.capture_button = QPushButton("Capture PNG")
        self.capture_button.clicked.connect(self._capture_current)
        self.capture_button.setEnabled(False)
        header_layout.addWidget(self.capture_button)

        right_layout.addWidget(header)

        self.preview_host = QFrame()
        self.preview_host.setFrameShape(QFrame.StyledPanel)
        self.preview_layout = QVBoxLayout(self.preview_host)
        self.preview_layout.setContentsMargins(8, 8, 8, 8)
        self.preview_layout.setSpacing(0)
        right_layout.addWidget(self.preview_host, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([270, 1230])

        self.setCentralWidget(root)
        self._populate_catalog()
        self.statusBar().showMessage("UI Lab prêt")
        self._select_first_live_preview()

    def _populate_catalog(self) -> None:
        groups: dict[str, QTreeWidgetItem] = {}
        for spec in default_previews():
            parent = groups.get(spec.group)
            if parent is None:
                parent = QTreeWidgetItem([spec.group])
                parent.setFlags(parent.flags() & ~Qt.ItemIsSelectable)
                groups[spec.group] = parent
                self.catalog.addTopLevelItem(parent)
            marker = "●" if spec.is_live else "○"
            item = QTreeWidgetItem([f"{marker}  {spec.label}"])
            item.setData(0, Qt.UserRole, spec.key)
            item.setToolTip(0, "Branché sur la vraie UI" if spec.is_live else "Squelette : à brancher")
            parent.addChild(item)
            parent.setExpanded(True)

    def _select_first_live_preview(self) -> None:
        for index in range(self.catalog.topLevelItemCount()):
            group = self.catalog.topLevelItem(index)
            for child_index in range(group.childCount()):
                child = group.child(child_index)
                key = child.data(0, Qt.UserRole)
                spec = self._specs.get(str(key))
                if spec is not None and spec.is_live:
                    self.catalog.setCurrentItem(child)
                    return

    def _on_current_item_changed(self, current: QTreeWidgetItem | None, _previous) -> None:
        if current is None:
            return
        key = current.data(0, Qt.UserRole)
        if not key:
            return
        spec = self._specs.get(str(key))
        if spec is not None:
            self._load_preview(spec)

    def _clear_preview(self) -> None:
        while self.preview_layout.count():
            item = self.preview_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._current_preview = None

    def _load_preview(self, spec: PreviewSpec) -> None:
        self._clear_preview()
        self._current_spec = spec
        self.preview_title.setText(spec.label)
        status = "LIVE — vraie UI" if spec.is_live else "SQUELETTE — non branché"
        self.preview_meta.setText(f"{status}  •  {spec.source}\n{spec.description}")
        self.reload_button.setEnabled(spec.is_live)
        self.capture_button.setEnabled(False)

        if not spec.is_live:
            self._show_planned(spec)
            self.statusBar().showMessage(f"{spec.label} : à brancher")
            return

        try:
            factory = resolve_factory(spec)
            context = PreviewContext(
                sandbox_root=Path(self._sandbox.name),
                report_status=self._report_preview_status,
            )
            widget = factory(context)
        except Exception:
            self._show_error(spec, traceback.format_exc())
            self.statusBar().showMessage(f"Erreur de chargement : {spec.label}")
            return

        self._current_preview = widget
        self.preview_layout.addWidget(widget, 1)
        self.capture_button.setEnabled(True)
        self.statusBar().showMessage(f"{spec.label} chargé depuis la vraie UI")

    def _show_planned(self, spec: PreviewSpec) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addStretch(1)
        title = QLabel(f"{spec.label} n'est pas encore branché au UI Lab.")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        layout.addWidget(title)
        detail = QLabel(
            "Le catalogue est déjà prêt. La prochaine étape consiste uniquement à ajouter une factory "
            "qui instancie le widget produit existant — aucune copie d'interface."
        )
        detail.setObjectName("MutedLabel")
        detail.setAlignment(Qt.AlignCenter)
        detail.setWordWrap(True)
        layout.addWidget(detail)
        layout.addStretch(1)
        self.preview_layout.addWidget(panel, 1)

    def _show_error(self, spec: PreviewSpec, details: str) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        title = QLabel(f"Impossible de charger {spec.label}")
        title.setWordWrap(True)
        layout.addWidget(title)
        log = QTextEdit()
        log.setReadOnly(True)
        log.setPlainText(details)
        layout.addWidget(log, 1)
        self.preview_layout.addWidget(panel, 1)

    def _report_preview_status(self, message: str) -> None:
        self.statusBar().showMessage(str(message))

    def _reload_current(self) -> None:
        if self._current_spec is not None:
            self._load_preview(self._current_spec)

    def _capture_current(self) -> None:
        if self._current_preview is None or self._current_spec is None:
            return
        safe_name = self._current_spec.key.replace(".", "-") + ".png"
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Enregistrer la capture UI Lab",
            safe_name,
            "Image PNG (*.png)",
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        if self._current_preview.grab().save(path, "PNG"):
            self.statusBar().showMessage(f"Capture enregistrée : {path}")
            return
        QMessageBox.warning(self, "UI Lab", "La capture PNG n'a pas pu être enregistrée.")

    def closeEvent(self, event) -> None:
        self._clear_preview()
        self._sandbox.cleanup()
        super().closeEvent(event)
