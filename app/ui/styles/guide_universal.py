from __future__ import annotations

from app.ui.theme import render_theme_template


_GUIDE_UNIVERSAL_STYLE = """
#GuideUltimeGeneratedView {
    background: @BG;
}

#GuideRouteHeader,
#GuideUltimeRouteSheet {
    background: @PANEL;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
}

#GuideUltimeRouteSheet[state="active"] {
    background: @PANEL;
    border-color: @GREEN_BORDER;
}

#GuideRouteTitle {
    color: @TEXT;
    font-size: 16px;
    font-weight: 800;
}

#GuideRoutePercent {
    color: @GREEN;
    font-size: 14px;
    font-weight: 800;
}

#GuideRouteProgress {
    background: @PANEL_2;
    border: none;
    border-radius: 3px;
}

#GuideRouteProgress::chunk {
    background: @GREEN;
    border-radius: 3px;
}

#GuideRouteInlineOrder {
    background: @PANEL;
    border: 1px solid @GREEN_BORDER;
    border-radius: @RADIUS_XS;
    color: @TEXT_SOFT;
}

#GuideRouteNav {
    background: transparent;
    border: none;
}

#GuideRouteLocation {
    color: @TEXT;
    font-size: 19px;
    font-weight: 800;
}

#GuideUltimeSectionTitle {
    color: @GREEN;
    font-size: 14px;
    font-weight: 800;
    margin-top: 6px;
}

#GuideRouteAction,
#GuideRouteNext,
#GuideRouteImportant {
    color: @TEXT_SOFT;
    font-size: 14px;
}

#GuideRouteImportant {
    color: @TEXT;
    font-weight: 700;
}

#GuideRouteAction[state="done"] {
    color: @TEXT_DISABLED;
}

#GuideRouteNext {
    color: @TEXT;
    font-weight: 700;
    margin-top: 8px;
}

#GuideRoutePageCheck {
    color: @TEXT;
    background: @PANEL_2;
    border: 1px solid @GREEN_BORDER;
    border-radius: @RADIUS_XS;
    padding: 10px 14px;
    spacing: 10px;
    font-size: 14px;
    font-weight: 800;
}

#GuideRoutePageCheck:disabled {
    color: @GREEN;
}

#GuideRoutePageCheck::indicator {
    width: 19px;
    height: 19px;
}

#GuideUltimeGeneratedView QPushButton,
#GuideUltimeGeneratedView QComboBox {
    background: @PANEL_HOVER;
    color: @TEXT_SOFT;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_XS;
    padding: 6px 10px;
}

#GuideUltimeGeneratedView QPushButton:hover,
#GuideUltimeGeneratedView QComboBox:hover {
    border-color: @GREEN_BORDER;
}

#GuideRouteCurrent {
    color: @GREEN;
    font-weight: 750;
}

QLabel[travelCopyEnabled="true"] {
    color: @GREEN;
}

QLabel[travelCopyEnabled="true"]:hover {
    text-decoration: underline;
}
"""


def guide_universal_stylesheet() -> str:
    return render_theme_template(_GUIDE_UNIVERSAL_STYLE)
