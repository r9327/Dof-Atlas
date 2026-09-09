from __future__ import annotations

from app.ui.theme import render_theme_template


_GUIDE_MANUAL_STYLE = """
QFrame#GuideBreadcrumb {
    background: @PANEL;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_SM;
}

QPushButton#GuideBreadcrumbButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: @RADIUS_XS;
    color: @TEXT_MUTED;
    font-size: @FONT_SMALL;
    font-weight: 700;
    min-height: 22px;
    max-height: 22px;
    padding: 0px @SPACE_MD;
    text-align: left;
}

QPushButton#GuideBreadcrumbButton:hover {
    background: @PANEL_HOVER;
    border-color: @GREEN_BORDER;
    color: @TEXT;
}

QLabel#GuideBreadcrumbSeparator,
QLabel#GuideBreadcrumbCurrent {
    color: @TEXT_MUTED;
    font-size: @FONT_SMALL;
}

#GuideManualProgressFrame,
#GuideManualNav {
    background: transparent;
    border: none;
}

#GuideManualProgress {
    background: @PANEL_2;
    border: 1px solid @BORDER_SOFT;
    border-radius: 3px;
}

#GuideManualProgress::chunk {
    background: @GREEN;
    border-radius: 2px;
}

#GuideManualPercent {
    color: @TEXT_SOFT;
    font-size: @FONT_BODY;
    font-weight: 700;
}

#GuideManualOrderChoice {
    background: @PANEL;
    border: 1px solid @GREEN_BORDER;
    border-radius: @RADIUS_XS;
}

#GuideManualOrderTitle {
    color: @TEXT;
    font-size: 15px;
    font-weight: 800;
}

#GuideManualOrderDetail {
    color: @TEXT_MUTED;
    font-size: @FONT_BODY;
}

#GuideManualOrderButton {
    background: @PANEL_HOVER;
    color: @TEXT_SOFT;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_XS;
    padding: 7px 10px;
    font-weight: 700;
}

#GuideManualOrderButton:hover {
    border-color: @GREEN_BORDER;
    color: @TEXT;
}

#GuideManualSheet {
    background: @PANEL;
    border: 1px solid @BORDER_SOFT;
    border-radius: @RADIUS_XS;
}

#GuideManualStageTitle {
    color: @TEXT;
    font-size: 17px;
    font-weight: 800;
}

#GuideManualLocation {
    color: @TEXT;
    font-size: 14px;
    font-weight: 800;
}

#GuideManualLine {
    color: @TEXT_SOFT;
    font-size: 14px;
    padding: 3px 0;
}

#GuideManualWarning {
    color: @DANGER_TEXT;
    background: @DANGER_PANEL;
    border: 1px solid @RED_DARK;
    border-radius: @RADIUS_XS;
    font-size: 14px;
    font-weight: 800;
    padding: 8px 10px;
}

#GuideManualCombat {
    color: @TEXT;
    background: @PANEL_2;
    border: 1px solid @RED_DARK;
    border-radius: @RADIUS_XS;
    font-size: 14px;
    font-weight: 700;
    padding: 8px 10px;
}

#GuideManualSpecial {
    color: @TEXT;
    background: @PANEL_HOVER;
    border: 1px solid @GREEN_BORDER;
    border-radius: @RADIUS_XS;
    font-size: 14px;
    font-weight: 700;
    padding: 8px 10px;
}

#GuideManualSuccessBlock {
    background: @PANEL_2;
    border: 1px solid @GREEN_BORDER;
    border-radius: @RADIUS_XS;
}

#GuideManualSuccessTitle {
    color: @TEXT;
    font-size: @FONT_BODY;
    font-weight: 800;
}

#GuideManualSuccessCheck {
    color: @TEXT_SOFT;
    background: transparent;
    spacing: 8px;
    font-size: 13px;
    font-weight: 700;
}

#GuideManualSuccessCheck[state="done"] {
    color: @GREEN;
}

#GuideManualSuccessCheck::indicator {
    width: 16px;
    height: 16px;
}

#GuideManualSuccessOpen {
    background: transparent;
    color: @TEXT_MUTED;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_XS;
    padding: 4px 8px;
    font-size: @FONT_SMALL;
    font-weight: 700;
}

#GuideManualSuccessOpen:hover {
    color: @TEXT;
    border-color: @GREEN_BORDER;
    background: @PANEL_HOVER;
}

#GuideManualSuccessOpen:disabled {
    color: @TEXT_DISABLED;
    border-color: @BORDER_SOFT;
}

#GuideManualNext {
    color: @GREEN;
    font-size: 14px;
    font-weight: 700;
    margin-top: 7px;
}

#GuideManualPageCheck {
    color: @TEXT_MUTED;
    background: transparent;
    border-top: 1px solid @BORDER_SOFT;
    padding: 10px 2px 2px 2px;
    spacing: 9px;
    font-size: 12px;
    font-weight: 700;
}

#GuideManualPageCheck:disabled {
    color: @GREEN;
}

#GuideManualPageCheck::indicator {
    width: 16px;
    height: 16px;
}

#GuideManualPrev,
#GuideManualNextButton {
    background: @PANEL_HOVER;
    color: @TEXT_SOFT;
    border: 1px solid @BORDER;
    border-radius: @RADIUS_XS;
    padding: 5px 12px;
    font-weight: 700;
}

#GuideManualPrev:hover,
#GuideManualNextButton:hover {
    border-color: @GREEN_BORDER;
    color: @TEXT;
}

QLabel[travelCopyEnabled="true"] {
    color: @GREEN;
}
"""


def guide_manual_stylesheet() -> str:
    return render_theme_template(_GUIDE_MANUAL_STYLE)