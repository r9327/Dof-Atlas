from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton

from app.constants import LOGO_PATH
from app.modules.encyclopedia.models.reward import Reward
from app.modules.encyclopedia.services.image_service import ENCYCLOPEDIA_IMAGE_SERVICE


class RewardCard(QFrame):
    def __init__(self, reward: Reward, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("RewardCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)
        icon = QToolButton()
        icon.setObjectName("RewardIcon")
        icon.setFixedSize(28, 28)
        icon.setIconSize(QSize(24, 24))

        image_path = Path(reward.image_path) if reward.image_path else None
        if image_path is None or not image_path.exists():
            image_path = LOGO_PATH if LOGO_PATH.exists() else None
        if image_path is not None:
            pixmap = ENCYCLOPEDIA_IMAGE_SERVICE.load_scaled(image_path, QSize(24, 24))
            if not pixmap.isNull():
                icon.setIcon(QIcon(pixmap))

        icon.setEnabled(False)
        label = QLabel(self.label_for(reward))
        label.setObjectName("CompactLabel")
        label.setWordWrap(True)
        layout.addWidget(icon)
        layout.addWidget(label, 1)

    @staticmethod
    def label_for(reward: Reward) -> str:
        quantity = reward.quantity
        if reward.kind == "achievement_points":
            return f"{quantity or 0} point(s) de succès"
        if reward.kind == "xp_ratio":
            return f"Expérience · ratio {quantity}"
        if reward.kind == "kamas_ratio":
            return f"Kamas · ratio {quantity}"
        if quantity and quantity > 1:
            return f"x{quantity} {reward.name}"
        return reward.name
