"""Lightweight Tk launcher chrome matching Atlas' default Qt design tokens.

Keep this module stdlib-only: the standalone updater must not import PySide6
or game data before it has verified and started the installed application.
"""
from __future__ import annotations

# Mirror the *default* palette in app.ui.theme.PALETTE. We intentionally avoid
# importing the Qt application (or optional unlicensed Unity assets) here.
COLORS = {
    "background": "#050A0D",
    "panel": "#081113",
    "border": "#26332D",
    "track": "#1C2925",
    "text": "#F5F7F2",
    "muted": "#AEB7B1",
    "accent": "#9FC528",
    "accent_hover": "#B9D94B",
    "danger": "#D71920",
}


def phase_for_message(message: str) -> str:
    """Human-readable startup phase; never claim a completed preload early."""
    normalized = message.casefold()
    if "echec" in normalized or "erreur" in normalized:
        return "ERREUR"
    if "hors ligne" in normalized or "indisponible" in normalized:
        return "MODE HORS LIGNE"
    if "differentiel" in normalized or "telechargement" in normalized:
        return "TÉLÉCHARGEMENT"
    if "installation" in normalized or "verification des fichiers" in normalized:
        return "INSTALLATION"
    if "lancement" in normalized or "est pret" in normalized:
        return "OUVERTURE D'ATLAS"
    if "verification des mises" in normalized or "est a jour" in normalized:
        return "VÉRIFICATION GITHUB"
    return "PRÉPARATION"


def add_header(tk, window) -> None:
    """Show the same near-black/olive identity as the application."""
    header = tk.Frame(window, bg=COLORS["background"], padx=30, pady=0)
    header.pack(fill="x", padx=0, pady=(17, 0))
    tk.Frame(header, bg=COLORS["accent"], height=3).pack(fill="x", pady=(0, 16))
    tk.Label(
        header, text="ATLAS  /  DESKTOP", bg=COLORS["background"],
        fg=COLORS["accent"], font=("Segoe UI", 9, "bold"), anchor="w",
    ).pack(fill="x")
    tk.Label(
        header, text="DOFUS ATLAS", bg=COLORS["background"],
        fg=COLORS["text"], font=("Segoe UI", 24, "bold"), anchor="w",
    ).pack(fill="x", pady=(2, 2))
    tk.Label(
        header, text="Lancement, mises à jour et préparation des données",
        bg=COLORS["background"], fg=COLORS["muted"],
        font=("Segoe UI", 10), anchor="w",
    ).pack(fill="x", pady=(0, 3))


def add_footer(tk, window) -> None:
    footer = tk.Frame(window, bg=COLORS["background"], padx=30)
    footer.pack(side="bottom", fill="x", pady=(0, 14))
    tk.Frame(footer, bg=COLORS["border"], height=1).pack(fill="x", pady=(0, 10))
    tk.Label(
        footer, text="CANAL STABLE  ·  GITHUB RELEASES",
        bg=COLORS["background"], fg=COLORS["muted"],
        font=("Segoe UI", 8), anchor="w",
    ).pack(fill="x")


def progress_style(style) -> None:
    style.theme_use("clam")
    style.configure(
        "Atlas.Horizontal.TProgressbar",
        troughcolor=COLORS["track"],
        background=COLORS["accent"],
        borderwidth=0,
        thickness=12,
        lightcolor=COLORS["accent"],
        darkcolor=COLORS["accent"],
    )


def button_options() -> dict:
    return {
        "bg": COLORS["accent"],
        "fg": COLORS["background"],
        "activebackground": COLORS["accent_hover"],
        "activeforeground": COLORS["background"],
        "font": ("Segoe UI", 10, "bold"),
        "relief": "flat",
        "bd": 0,
        "padx": 16,
        "pady": 8,
        "cursor": "hand2",
    }
