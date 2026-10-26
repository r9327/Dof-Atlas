"""Minimal standalone Tk chrome; no Qt/game imports or third-party assets.

The two palettes mirror app.ui.theme.PALETTE and
app.ui.unity_skin.UNITY_PALETTE. The real Atlas icon is an embedded 64px
PNG frame extracted from data/images/misc/dofus_atlas.ico (project icon),
so the onefile Windows launcher needs no separate asset on disk.
"""
from __future__ import annotations

import os

ATLAS_PALETTE = {
    "background": "#050A0D",
    "panel": "#081113",
    "border": "#26332D",
    "track": "#1C2925",
    "text": "#F5F7F2",
    "muted": "#AEB7B1",
    "accent": "#9FC528",
    "accent_hover": "#5C7E1B",
}
UNITY_PALETTE = {
    "background": "#151821",
    "panel": "#1B2746",
    "border": "#475F89",
    "track": "#213154",
    "text": "#F1F6FB",
    "muted": "#B8C6E3",
    "accent": "#9FCE51",
    "accent_hover": "#B1DC64",
}


def palette_for_theme(theme: str) -> dict[str, str]:
    """Use precisely the same opt-in switch as app.ui.unity_skin."""
    return UNITY_PALETTE if theme.strip().casefold() == "dofus_unity" else ATLAS_PALETTE


COLORS = palette_for_theme(os.environ.get("ATLAS_THEME", ""))
FONT_FAMILY = "Lexend" if os.environ.get("ATLAS_THEME", "").strip().casefold() == "dofus_unity" else "Segoe UI"

# Exact existing Atlas application icon, not a substitute game logo.
LOGO_PNG_BASE64 = (
    "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"
    "ge3phIaNY9MVzYD2VNP/rx5oo68vqwmcqQXc9rPDPLqvysW71vDKV6bYtMkjlYrwfcGRQz73/qrC0OEqb7hsFWnHoK9buV"
    "vB5HSNxw7leeS5Mv/l6rP5y7+I6Os6Sq1eJQjCWZUzicIEe552+Ye/r5IvGByalBrLyFYcIGezN+UGrGo3GBkx+Oz/EXzq"
    "75VLkhimSlUJ/ZlyBVFoMDVVJJl4nI//r40MrNnKzV88SDoRUq2HGiAdGcsxPVWkVAfTkpy1oYutA1ktIX61wXQt5HO3Pk"
    "uyq5Nbvnoul108iiGOIYSnoXapDJddnOTgUYdf3VPHeYnJxoEMR8ZrPLBnQjPzyFidV75+M5+7oUph5lkmpy3SabVOS0vc"
    "9FRIJhNw+10Vjpy0MSxnnim05pn+2a/jBcH6AYt7H/DZ/aTJxZfEBL4KOw1832L30zZdHbB9C0SBzejwMf7gPQ2OHe3lFz"
    "8Zpz2bZOhEntGShFe/nc6zttBz/DC/uePHTBY8oihkw7oOvvQfh9hyfoYbP5/CNh+lVAoJohRPP5PWVvzFuyK+fmvAF75U"
    "Y1N/kqGxKrl8nYf2TlHAIZNyyPS288EPRExNPkMQpREm3PrdiIOHIy48z+D1Vxv88Mdw89cCtg1aDM80Y5k5K2i1ugTFGS"
    "UFFU+pmknKNrnj5zEXXiBo1GGgV7B3n+D6d1dIOoJXvCzBpz9m09WZZGJynHe+o49f39NEfjXbJf+u/076ypfwvvM3cyJ3"
    "kIGzBvnlp79Ad1uN/SN1ZnyfL3/EJgoPUK5Y5Isuf/aRgPsfqmJZ8I8fz3DTLT6OkNix5OH9ORIpB5Hp4O3XZli7psEdPy"
    "3RkZ2gXHbItsX85d+F3HpbcIqmv/hwil/c7dPTYdLwhXbrtnk6sWYsggqz9mC6YrC2z+b+B+CnPxNarMJIkEzGuG5MuSL5"
    "8U+qvP/PGkiprL5J/6oyZ58bM5bzKVz9do6vGuCC1avY2LGGoYpgYtMAu957HY89N8W+E0X2H61y591lwtjRO3fD5z3uf6"
    "BB2kWjxb/9ZImpiSRXvWQ91797C+VI4HYJvvWtFB/6owkEw4zPKCOqYLnyLjA+obChpLvbwk2Z3Py1GsOjkq6MRb7adOet"
    "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"
    "sXn/5/dG1R8G22ZywAAAAASUVORK5CYII="
)


def display_message(message: str) -> str:
    """Keep one useful status line, without duplicated transfer percentages."""
    for prefix, description in (
        ("Differentiel :", "Téléchargement des fichiers modifiés…"),
        ("Telechargement :", "Téléchargement de la mise à jour…"),
        ("Installation differentielle", "Installation des fichiers modifiés…"),
        ("Verification des fichiers", "Vérification des fichiers…"),
    ):
        if message.startswith(prefix):
            return description
    return message


def add_header(tk, window) -> None:
    """Only product icon and application title, no navigation or decorative UI."""
    header = tk.Frame(window, bg=COLORS["background"])
    header.pack(fill="x", pady=(24, 0))
    try:
        logo = tk.PhotoImage(data=LOGO_PNG_BASE64, format="png")
        icon = tk.Label(header, image=logo, bg=COLORS["background"])
        icon.image = logo  # Tk images need a live Python reference.
        icon.pack(pady=(0, 11))
    except (tk.TclError, ValueError):
        # Displaying a damaged icon must not block a safe update or startup.
        pass
    tk.Label(
        header, text="Dofus Atlas", bg=COLORS["background"],
        fg=COLORS["text"], font=(FONT_FAMILY, 20, "bold"),
    ).pack()


def progress_style(style) -> None:
    style.theme_use("clam")
    style.configure(
        "Atlas.Horizontal.TProgressbar",
        troughcolor=COLORS["track"], background=COLORS["accent"],
        borderwidth=0, thickness=12,
        lightcolor=COLORS["accent"], darkcolor=COLORS["accent"],
    )


def button_options() -> dict[str, object]:
    """For first-install folder selection only, never the normal startup."""
    return {
        "bg": COLORS["accent"],
        "fg": COLORS["background"],
        "activebackground": COLORS["accent_hover"],
        "activeforeground": COLORS["background"],
        "font": ("Lexend", 10, "bold"),
        "relief": "flat", "bd": 0, "padx": 16, "pady": 8,
        "cursor": "hand2",
    }
