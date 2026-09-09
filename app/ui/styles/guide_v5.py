from __future__ import annotations

from app.ui.theme import render_theme_template


_GUIDE_V5_STYLE = """
#GuideUltimeGeneratedView {
    background: @BG;
}

#GuideUltimeProgressHeader {
    background: @PANEL;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_SM;
}

#GuideUltimeTitle {
    color: @TEXT;
    font-size: 18px;
    font-weight: 800;
}

#GuideUltimeProgressText {
    color: @GREEN;
    font-weight: 800;
    font-size: 14px;
}

#GuideUltimeProgressDetails,
#GuideUltimeBranchStatus,
#GuideUltimePosition {
    color: @TEXT_MUTED;
}

#GuideUltimeProgressBar {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
}

#GuideUltimeProgressBar::chunk {
    background: @GREEN;
    border-radius: 3px;
}

#GuideUltimeNav {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
}

#GuideUltimeCard {
    background: @PANEL;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_SM;
}

#GuideUltimeCard[state="active"] {
    border: 1px solid @GREEN_BORDER;
    background: @PANEL_ACTIVE;
}

#GuideUltimeCard[state="done"] {
    background: @PANEL_2;
    border-color: @BORDER_SOFT;
}

#GuideUltimeCardLevel {
    color: @TEXT;
    font-weight: 800;
}

#GuideUltimeCardLocation,
#GuideUltimeCompactSummary {
    color: @TEXT_MUTED;
}

#GuideUltimeSectionTitle {
    color: @GREEN;
    font-weight: 800;
    margin-top: 4px;
}

#GuideUltimeDoneBadge {
    color: @TEXT_DISABLED;
    font-weight: 700;
}

#GuideUltimeActiveBadge {
    color: @GREEN;
    font-weight: 800;
}

#GuideUltimeInfoLine,
#GuideUltimeNextLine {
    color: @TEXT_SOFT;
}

#GuideUltimeInfoLine[state="done"] {
    color: @TEXT_DISABLED;
}

#GuideUltimeGeneratedView QCheckBox {
    color: @TEXT_SOFT;
    spacing: 8px;
}

#GuideUltimeGeneratedView QCheckBox[state="done"] {
    color: @TEXT_DISABLED;
}

#GuideUltimeGeneratedView QCheckBox::indicator {
    width: 16px;
    height: 16px;
}

#GuideUltimeGeneratedView QComboBox,
#GuideUltimeGeneratedView QPushButton,
#GuideUltimeGeneratedView QToolButton {
    background: @PANEL_HOVER;
    color: @TEXT_SOFT;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_XS;
    padding: 4px 8px;
}

#GuideUltimeGeneratedView QComboBox:hover,
#GuideUltimeGeneratedView QPushButton:hover,
#GuideUltimeGeneratedView QToolButton:hover {
    border-color: @GREEN_BORDER;
}
"""


def guide_v5_stylesheet() -> str:
    return render_theme_template(_GUIDE_V5_STYLE)
