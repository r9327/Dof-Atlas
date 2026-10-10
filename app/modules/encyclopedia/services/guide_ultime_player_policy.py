from __future__ import annotations

import copy
import re
from typing import Any

from app.core.text import normalize_key as normalize_text


_ACTION_START_RE = re.compile(
    r"\b(?:"
    r"va|aller|rends[- ]?toi|retourne|reviens|parle(?:r)?|discute(?:r)?|"
    r"prends|prendre|lance(?:r)?|entre(?:r)?|rejoins|rejoindre|"
    r"t[ée]l[ée]porte(?:r)?|utilise(?:r)?|ach[èe]te(?:r)?|"
    r"drop|droppe|dropper|tue(?:r)?|fais|faire|bats|battre|"
    r"ramasse(?:r)?|donne(?:r)?|clique(?:r)?|ouvre(?:r)?|termine(?:r)?|"
    r"valide(?:r)?|gagne(?:r)?|vaincs|vaincre|capture(?:r)?|"
    r"craft(?:e|er)?|fabrique(?:r)?|r[ée]colte(?:r)?|cueille|cueillir|"
    r"p[êe]che(?:r)?|mine(?:r)?|choisis|choisir|v[ée]rifie(?:r)?|"
    r"encha[îi]ne(?:r)?|avance(?:r)?|obtiens|obtenir|r[ée]cup[èe]re(?:r)?|"
    r"[ée]change(?:r)?|regroupe(?:r)?"
    r")\b",
    flags=re.IGNORECASE,
)
_BOUNDARY_RE = re.compile(
    r"(?P<sep>\s*(?:[;,]|\b(?:puis|ensuite|et)\b)\s*)"
    r"(?=(?:(?:le|la|les|l['’])\s+)?"
    r"(?:va|aller|rends[- ]?toi|retourne|reviens|parle(?:r)?|discute(?:r)?|"
    r"prends|prendre|lance(?:r)?|entre(?:r)?|rejoins|rejoindre|"
    r"t[ée]l[ée]porte(?:r)?|utilise(?:r)?|ach[èe]te(?:r)?|"
    r"drop|droppe|dropper|tue(?:r)?|fais|faire|bats|battre|"
    r"ramasse(?:r)?|donne(?:r)?|clique(?:r)?|ouvre(?:r)?|termine(?:r)?|"
    r"valide(?:r)?|gagne(?:r)?|vaincs|vaincre|capture(?:r)?|"
    r"craft(?:e|er)?|fabrique(?:r)?|r[ée]colte(?:r)?|cueille|cueillir|"
    r"p[êe]che(?:r)?|mine(?:r)?|choisis|choisir|v[ée]rifie(?:r)?|"
    r"encha[îi]ne(?:r)?|avance(?:r)?|obtiens|obtenir|r[ée]cup[èe]re(?:r)?|"
    r"[ée]change(?:r)?)\b)",
    flags=re.IGNORECASE,
)
_SENTENCE_BOUNDARY_RE = re.compile(
    r"(?<=[.!?])\s+(?=(?:Puis\s+|Ensuite\s+)?"
    r"(?:(?:Avec|Une fois|Après|Quand|Lorsque)\b[^,.!?]*,\s*)?"
    r"(?:Va|Aller|Rends[- ]?toi|Retourne|Reviens|Parle|Parler|Discute|Discuter|"
    r"Prends|Prendre|Lance|Lancer|Entre|Entrer|Rejoins|Rejoindre|Téléporte|Téléporter|"
    r"Utilise|Utiliser|Achète|Acheter|Drop|Droppe|Dropper|Tue|Tuer|Fais|Faire|Bats|Battre|"
    r"Ramasse|Ramasser|Donne|Donner|Clique|Cliquer|Ouvre|Ouvrir|Termine|Terminer|"
    r"Valide|Valider|Gagne|Gagner|Vaincs|Vaincre|Capture|Capturer|Crafte|Crafter|Fabrique|Fabriquer|"
    r"Récolte|Récolter|Cueille|Cueillir|Pêche|Pêcher|Mine|Miner|Choisis|Choisir|Vérifie|Vérifier|"
    r"Enchaîne|Enchaîner|Avance|Avancer|Obtiens|Obtenir|Récupère|Récupérer|Échange|Échanger|"
    r"Regroupe|Regrouper)\b)",
    flags=re.IGNORECASE,
)
_CONSEQUENCE_LEFT_RE = re.compile(
    r"\b(?:se\s+(?:termine|ferme)|(?:la|cette|ce)\s+(?:qu[êe]te|victoire|combat|mission|[ée]tape)\b|cela\s+(?:permet|ouvre|d[ée]bloque)|\bpermet\b)",
    flags=re.IGNORECASE,
)
_DROP_ACTION_RE = re.compile(r"\b(?:drop|droppe|dropper)\b", flags=re.IGNORECASE)
_PURCHASE_RE = re.compile(
    r"\b(?:achet\w*|ach[èe]t\w*|achat\w*|hdv|h[ôo]tel\s+de\s+vente)\b",
    flags=re.IGNORECASE,
)
_ACQUIRE_RE = re.compile(
    r"\b(?:achet\w*|ach[èe]t\w*|drop|droppe|dropper|r[ée]colt\w*|cueill\w*|"
    r"p[êe]ch\w*|min\w*|ramass\w*|r[ée]cup[èe]r\w*|obti\w*|obten\w*|"
    r"craft\w*|fabriqu\w*|prends|prendre|[ée]chang\w*)\b",
    flags=re.IGNORECASE,
)
_ACQUISITION_CLAUSE_SPLIT_RE = re.compile(
    r"\s*(?:[,;.!?]|\b(?:puis|ensuite)\b)\s*",
    flags=re.IGNORECASE,
)
_RESOURCE_TRAILING_CONNECTORS = {
    "a",
    "apres",
    "au",
    "aux",
    "avant",
    "avec",
    "chez",
    "contre",
    "dans",
    "en",
    "et",
    "pour",
    "puis",
    "sur",
}


def _has_player_action(text: str) -> bool:
    return _ACTION_START_RE.search(str(text or "")) is not None


def _is_consequence_boundary(text: str, boundary_start: int) -> bool:
    sentence_start = max(
        text.rfind(".", 0, boundary_start),
        text.rfind("!", 0, boundary_start),
        text.rfind("?", 0, boundary_start),
    )
    left = text[sentence_start + 1 : boundary_start]
    return _CONSEQUENCE_LEFT_RE.search(left) is not None


def split_real_actions(text: str) -> list[str]:
    """Split only proven player actions; keep narrative consequences attached."""
    value = " ".join(str(text or "").split()).strip()
    if not value:
        return []

    sentence_parts = [part.strip() for part in _SENTENCE_BOUNDARY_RE.split(value) if part.strip()]
    result: list[str] = []
    for sentence in sentence_parts:
        start = 0
        for match in _BOUNDARY_RE.finditer(sentence):
            left = sentence[start : match.start()].strip()
            local_start = max(left.rfind("."), left.rfind("!"), left.rfind("?")) + 1
            local_left = left[local_start:].strip()
            sep = match.group("sep").strip().casefold()
            if not left or not _has_player_action(local_left):
                continue
            if sep in {",", ";"} and local_left.casefold().startswith(("après ", "apres ")):
                after_intro_comma = local_left.split(",", 1)[1].strip() if "," in local_left else ""
                if not after_intro_comma or _ACTION_START_RE.match(after_intro_comma) is None:
                    continue
            if _is_consequence_boundary(sentence, match.start()):
                continue
            result.append(left.rstrip(" ,;"))
            start = match.end()
        tail = sentence[start:].strip()
        if tail:
            result.append(tail)
    return result or [value]


def has_actionable_drop(text: str) -> bool:
    return _DROP_ACTION_RE.search(str(text or "")) is not None


def has_purchase_alternative(text: str) -> bool:
    return _PURCHASE_RE.search(str(text or "")) is not None


def ensure_drop_purchase_alternative(text: str) -> str:
    value = " ".join(str(text or "").split()).strip()
    if has_actionable_drop(value) and not has_purchase_alternative(value):
        return value.rstrip() + " Alternative : achat en HDV possible."
    return value


def _resource_name_matches(text: str, resource_name: str) -> bool:
    """Match the exact normalized item phrase, not a prefix or word fragment."""
    resource_tokens = [token for token in normalize_text(resource_name).split("_") if token]
    text_tokens = [token for token in normalize_text(text).split("_") if token]
    if not resource_tokens or len(resource_tokens) > len(text_tokens):
        return False

    width = len(resource_tokens)
    for index in range(len(text_tokens) - width + 1):
        if text_tokens[index : index + width] != resource_tokens:
            continue
        next_index = index + width
        if next_index >= len(text_tokens):
            return True
        if text_tokens[next_index] in _RESOURCE_TRAILING_CONNECTORS:
            return True
    return False


def line_acquires_resource(text: str, resource_name: str) -> bool:
    """Require the acquisition verb and resource to live in the same clause."""
    for clause in _ACQUISITION_CLAUSE_SPLIT_RE.split(str(text or "")):
        if not clause:
            continue
        if _resource_name_matches(clause, resource_name) and _ACQUIRE_RE.search(clause):
            return True
    return False


def preparation_resource_name(text: str) -> str:
    value = " ".join(str(text or "").split()).strip()
    if not value.casefold().startswith("prépare ") and not value.casefold().startswith("prepare "):
        return ""
    head = value.split(".", 1)[0]
    payload = head.split(" ", 1)[1].strip() if " " in head else ""
    if " × " in payload:
        payload = payload.split(" × ", 1)[1].strip()
    return payload


def apply_player_line_policy(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply Phase 7E player-facing rules without mutating canonical route data."""
    expanded: list[dict[str, Any]] = []
    for raw in lines:
        if not isinstance(raw, dict):
            continue
        row = copy.deepcopy(raw)
        kind = str(row.get("kind") or "").strip()
        text = " ".join(str(row.get("text") or "").split()).strip()
        if kind != "action":
            row["text"] = text
            expanded.append(row)
            continue
        for part in split_real_actions(text):
            split_row = copy.deepcopy(row)
            split_row["text"] = ensure_drop_purchase_alternative(part)
            expanded.append(split_row)

    action_texts = [
        str(row.get("text") or "")
        for row in expanded
        if str(row.get("kind") or "") == "action"
    ]
    filtered: list[dict[str, Any]] = []
    for row in expanded:
        if str(row.get("kind") or "") == "warning":
            resource_name = preparation_resource_name(str(row.get("text") or ""))
            if resource_name and any(line_acquires_resource(text, resource_name) for text in action_texts):
                continue
        filtered.append(row)

    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in filtered:
        key = (
            str(row.get("kind") or "").strip(),
            str(row.get("position") or "").strip(),
            normalize_text(row.get("text")),
        )
        if key[2] and key not in seen:
            seen.add(key)
            result.append(row)
    return result
