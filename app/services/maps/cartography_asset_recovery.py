from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, UnidentifiedImageError

from app.constants import DATA_DIR, LOGGER, ROOT_DIR
from app.services.maps.map_manifest import MAP_RAW_DIR, ensure_cache_layout, write_json

SOURCES_PATH = DATA_DIR / "cartography" / "sources.json"
MAP_VIEWS_PATH = DATA_DIR / "cartography" / "map_views.json"
REJECTED_DIR = DATA_DIR / "cartography" / "assets" / "_rejected"
CANDIDATE_DIR = DATA_DIR / "cache" / "dofus_maps" / "raw" / "candidates"
PREVIEW_DIR = DATA_DIR / "reports" / "cartography_asset_previews"
USER_AGENT = "DofusAtlasAssetRecovery/1.0"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MIN_MAP_BYTES = 80_000
MIN_MAP_WIDTH = 512
MIN_MAP_HEIGHT = 320
REJECTED_DOFUS_DISCOVERY_REASON = "REJECTED: wrong map / not valid Dofus 3 Unity world map."
_FORBIDDEN_COMMAND_TOKENS = {"&&", "||", "|", ">", ">>", "<", "2>", "2>>", "&"}


@dataclass(frozen=True, slots=True)
class ExpectedWorldAsset:
    key: str
    view_key: str
    name: str
    asset_path: str
    aliases: tuple[str, ...]
    worldmap_ids: tuple[str, ...] = ()

    @property
    def destination(self) -> Path:
        return ROOT_DIR / self.asset_path


@dataclass(slots=True)
class AssetValidation:
    ok: bool
    path: str
    width: int = 0
    height: int = 0
    bytes: int = 0
    error: str = ""


@dataclass(slots=True)
class RecoveryResult:
    source: str
    asset_key: str
    status: str
    message: str
    source_path: str = ""
    destination_path: str = ""
    width: int = 0
    height: int = 0
    bytes: int = 0
    archive_member: str = ""
    preview_path: str = ""
    requires_human_validation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RecoveryReport:
    existing_before: dict[str, Any]
    existing_after: dict[str, Any]
    sources_tested: list[str] = field(default_factory=list)
    local_candidates: list[dict[str, Any]] = field(default_factory=list)
    results: list[RecoveryResult] = field(default_factory=list)
    map_views: dict[str, Any] = field(default_factory=dict)
    rejections: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "existing_before": self.existing_before,
            "existing_after": self.existing_after,
            "sources_tested": self.sources_tested,
            "local_candidates": self.local_candidates,
            "results": [result.to_dict() for result in self.results],
            "map_views": self.map_views,
            "rejections": self.rejections,
        }


def expected_world_assets() -> list[ExpectedWorldAsset]:
    return [
        ExpectedWorldAsset(
            key="world_amakna",
            view_key="world_amakna",
            name="Monde des Douze / Continent Amakneen",
            asset_path="data/cartography/assets/world/amakna/world.png",
            aliases=("world_amakna", "monde des douze", "amakna", "amakneen", "amaknean", "continent amakna"),
            worldmap_ids=("1",),
        ),
        ExpectedWorldAsset(
            key="dimension_enutrosor",
            view_key="dimension_enutrosor",
            name="Enutrosor",
            asset_path="data/cartography/assets/world/enutrosor/world.png",
            aliases=("dimension_enutrosor", "enutrosor", "enurado"),
            worldmap_ids=("13",),
        ),
    ]


def load_sources_config() -> dict[str, Any]:
    if not SOURCES_PATH.exists():
        return {"sources": {}}
    try:
        return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.error("[ScanMonde] sources.json invalide: %s", exc)
        return {"sources": {}}


def scan_existing_cartography_assets() -> dict[str, Any]:
    assets = {}
    for asset in expected_world_assets():
        validation = validate_recovered_asset(asset.destination)
        assets[asset.key] = {
            "view_key": asset.view_key,
            "name": asset.name,
            "asset_path": asset.asset_path,
            "destination": str(asset.destination),
            "exists": validation.ok,
            "width": validation.width,
            "height": validation.height,
            "bytes": validation.bytes,
            "error": validation.error,
        }
    return {
        "assets": assets,
        "missing": [key for key, row in assets.items() if not row["exists"]],
        "existing": [key for key, row in assets.items() if row["exists"]],
    }


def scan_rejected_assets() -> list[dict[str, Any]]:
    known_rejections = [
        {
            "asset_key": "world_amakna",
            "path": REJECTED_DIR / "amakna_wrong_dofus_discovery_world.png",
            "source": "dofus_discovery",
            "reason": REJECTED_DOFUS_DISCOVERY_REASON,
        },
        {
            "asset_key": "world_amakna",
            "path": REJECTED_DIR / "raw" / "dofus_discovery_rendered.jpg",
            "source": "dofus_discovery_raw",
            "reason": REJECTED_DOFUS_DISCOVERY_REASON,
        },
    ]
    rejections: list[dict[str, Any]] = []
    for row in known_rejections:
        path = Path(row["path"])
        validation = validate_recovered_asset(path)
        rejections.append(
            {
                "asset_key": row["asset_key"],
                "path": str(path),
                "exists": path.exists(),
                "source": row["source"],
                "reason": row["reason"],
                "width": validation.width,
                "height": validation.height,
                "bytes": validation.bytes,
            }
        )
    return rejections


def recover_missing_cartography_assets(
    *,
    allow_network: bool = True,
    allow_large_downloads: bool = False,
    run_doduda_cli: bool = True,
) -> RecoveryReport:
    ensure_cache_layout()
    config = load_sources_config()
    existing_before = scan_existing_cartography_assets()
    report = RecoveryReport(
        existing_before=existing_before,
        existing_after=existing_before,
        map_views=verify_map_views_paths(),
        rejections=scan_rejected_assets(),
    )
    missing = missing_assets(existing_before)
    if not missing:
        report.results.append(RecoveryResult("local", "", "ok", "Tous les assets attendus existent deja."))
        return report

    report.sources_tested.append("local/projet/backups")
    local_results, local_candidates = recover_from_local_project(missing, config)
    report.results.extend(local_results)
    report.local_candidates.extend(local_candidates)
    missing = missing_assets(scan_existing_cartography_assets())

    if missing:
        report.sources_tested.append("doduda")
        report.results.extend(
            recover_from_doduda(
                missing,
                config,
                allow_network=allow_network,
                allow_large_downloads=allow_large_downloads,
                run_cli=run_doduda_cli,
            )
        )
        missing = missing_assets(scan_existing_cartography_assets())

    if missing:
        report.sources_tested.append("dofus_discovery")
        report.results.extend(recover_from_dofus_discovery(missing, config, allow_network=allow_network))
        missing = missing_assets(scan_existing_cartography_assets())

    if missing:
        report.sources_tested.append("dofus_map")
        report.results.extend(recover_from_dofus_map(missing, config, allow_network=allow_network))
        missing = missing_assets(scan_existing_cartography_assets())

    if missing:
        for asset in missing:
            report.results.append(
                RecoveryResult(
                    "summary",
                    asset.key,
                    "missing",
                    "Impossible de recuperer les cartes : aucune source exploitable trouvee.",
                    destination_path=str(asset.destination),
                )
            )

    report.existing_after = scan_existing_cartography_assets()
    report.map_views = verify_map_views_paths()
    return report


def missing_assets(scan: dict[str, Any]) -> list[ExpectedWorldAsset]:
    missing_keys = set(scan.get("missing") or [])
    return [asset for asset in expected_world_assets() if asset.key in missing_keys]


def recover_from_local_project(
    missing: Iterable[ExpectedWorldAsset],
    config: dict[str, Any] | None = None,
) -> tuple[list[RecoveryResult], list[dict[str, Any]]]:
    config = config or load_sources_config()
    candidates = scan_local_image_candidates(config)
    results: list[RecoveryResult] = []
    missing_by_key = {asset.key: asset for asset in missing}
    for asset in missing_by_key.values():
        match = first_local_match(asset, candidates)
        if match is None:
            results.append(RecoveryResult("local", asset.key, "not_found", "Aucun candidat local fiable trouve."))
            continue
        results.append(
            stage_candidate_asset(
                Path(str(match["path"])),
                asset,
                "local",
            )
        )
    return results, candidates[:30]


def recover_from_doduda(
    missing: Iterable[ExpectedWorldAsset],
    config: dict[str, Any] | None = None,
    *,
    allow_network: bool = True,
    allow_large_downloads: bool = False,
    run_cli: bool = True,
) -> list[RecoveryResult]:
    config = config or load_sources_config()
    source = (config.get("sources") or {}).get("doduda") or {}
    results: list[RecoveryResult] = []
    missing_list = list(missing)
    if not source.get("enabled", False):
        return [RecoveryResult("doduda", asset.key, "skipped", "Source doduda desactivee.") for asset in missing_list]

    executable = find_doduda_executable(source)
    if executable:
        results.append(
            RecoveryResult(
                "doduda",
                "",
                "executable_available",
                f"doduda executable detecte: {executable}",
                source_path=executable,
            )
        )
    if executable and run_cli and source.get("run_cli_if_available", True) and source.get("allow_auto_cli_run", False):
        completed = run_recovery_commands(
            executable,
            source.get("command_args"),
        )
        results.append(
            RecoveryResult(
                "doduda",
                "",
                "command_ok" if completed[0] == 0 else "command_failed",
                completed[1],
            )
        )
        local_results, _candidates = recover_from_local_project(missing_list, config)
        copied = [result for result in local_results if result.status == "copied"]
        if copied:
            results.extend(copied)
            return results
    elif not executable:
        results.append(RecoveryResult("doduda", "", "not_installed", "doduda non installe ou introuvable dans PATH."))
    else:
        results.append(
            RecoveryResult(
                "doduda",
                "",
                "auto_cli_skipped",
                "Execution automatique de doduda desactivee; utilisez les commandes safe_* de sources.json.",
            )
        )

    if allow_network:
        results.extend(check_doduda_release_archive(missing_list, source, allow_large_downloads=allow_large_downloads))
    else:
        results.append(RecoveryResult("doduda", "", "network_disabled", "Reseau desactive pour cette execution."))
    return results


def find_doduda_executable(source: dict[str, Any]) -> str | None:
    configured = str(source.get("local_executable") or "").strip()
    if configured:
        path = resolve_project_path(configured)
        if path.exists() and path.is_file():
            return str(path)
    executable = shutil.which("doduda")
    return executable


def recover_from_dofus_discovery(
    missing: Iterable[ExpectedWorldAsset],
    config: dict[str, Any] | None = None,
    *,
    allow_network: bool = True,
) -> list[RecoveryResult]:
    config = config or load_sources_config()
    source = (config.get("sources") or {}).get("dofus_discovery") or {}
    results: list[RecoveryResult] = []
    missing_list = list(missing)
    if not source.get("enabled", False):
        return [
            RecoveryResult("dofus_discovery", asset.key, "skipped", "Source Dofus-Discovery desactivee.")
            for asset in missing_list
        ]
    if not allow_network:
        return [
            RecoveryResult("dofus_discovery", asset.key, "network_disabled", "Reseau desactive pour cette execution.")
            for asset in missing_list
        ]
    if not source.get("allow_as_final_source", False):
        rejected = source.get("rejected_as_final_for") or {}
        return [
            RecoveryResult(
                "dofus_discovery",
                asset.key,
                "blacklisted_final_source",
                str(rejected.get(asset.key) or "Dofus-Discovery reference technique uniquement, pas source finale."),
                requires_human_validation=True,
            )
            for asset in missing_list
        ]

    configured_assets = source.get("assets") or {}
    for asset in missing_list:
        entries = configured_assets.get(asset.key) or []
        if not entries:
            results.append(
                RecoveryResult(
                    "dofus_discovery",
                    asset.key,
                    "not_available",
                    "Aucun asset Dofus-Discovery configure pour cette vue.",
                )
            )
            continue
        copied = False
        for entry in entries:
            url = str(entry.get("url") or "")
            filename = str(entry.get("filename") or Path(url).name or f"{asset.key}.img")
            raw_path = MAP_RAW_DIR / "dofus_discovery" / filename
            try:
                download_file(url, raw_path)
            except OSError as exc:
                results.append(
                    RecoveryResult("dofus_discovery", asset.key, "download_failed", str(exc), source_path=url)
                )
                continue
            result = copy_asset_to_expected_path(
                raw_path,
                asset,
                "dofus_discovery",
                crop_box=entry.get("crop_box"),
            )
            results.append(result)
            if result.status == "copied":
                copied = True
                break
        if not copied:
            results.append(
                RecoveryResult(
                    "dofus_discovery",
                    asset.key,
                    "failed",
                    "Dofus-Discovery incompatible ou image recuperee invalide.",
                )
            )
    return results


def recover_from_dofus_map(
    missing: Iterable[ExpectedWorldAsset],
    config: dict[str, Any] | None = None,
    *,
    allow_network: bool = True,
) -> list[RecoveryResult]:
    config = config or load_sources_config()
    source = (config.get("sources") or {}).get("dofus_map") or {}
    missing_list = list(missing)
    if not source.get("enabled", False):
        return [
            RecoveryResult(
                "dofus_map",
                asset.key,
                "skipped",
                "Dofus-map.com non exploitable automatiquement sans scraping non propre.",
            )
            for asset in missing_list
        ]
    if not allow_network:
        return [
            RecoveryResult("dofus_map", asset.key, "network_disabled", "Reseau desactive pour cette execution.")
            for asset in missing_list
        ]
    configured_assets = source.get("asset_urls") or {}
    if not configured_assets:
        return [
            RecoveryResult(
                "dofus_map",
                asset.key,
                "not_configured",
                "Dofus-map.com non exploitable automatiquement sans scraping non propre.",
            )
            for asset in missing_list
        ]
    results: list[RecoveryResult] = []
    for asset in missing_list:
        url = str(configured_assets.get(asset.key) or "")
        if not url:
            results.append(
                RecoveryResult(
                    "dofus_map",
                    asset.key,
                    "not_configured",
                    "Aucune URL publique directe configuree pour cette vue.",
                )
            )
            continue
        raw_path = MAP_RAW_DIR / "dofus_map" / f"{asset.key}{Path(url).suffix or '.png'}"
        try:
            download_file(url, raw_path)
        except OSError as exc:
            results.append(RecoveryResult("dofus_map", asset.key, "download_failed", str(exc), source_path=url))
            continue
        results.append(copy_asset_to_expected_path(raw_path, asset, "dofus_map"))
    return results


def validate_recovered_asset(path: Path | str) -> AssetValidation:
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return AssetValidation(False, str(candidate), error="fichier absent")
    try:
        size = candidate.stat().st_size
    except OSError as exc:
        return AssetValidation(False, str(candidate), error=f"stat impossible: {exc}")
    if size < MIN_MAP_BYTES:
        return AssetValidation(False, str(candidate), bytes=size, error="image trop petite")
    try:
        with Image.open(candidate) as image:
            image.verify()
        with Image.open(candidate) as image:
            width, height = image.size
    except (OSError, UnidentifiedImageError) as exc:
        return AssetValidation(False, str(candidate), bytes=size, error=f"image invalide: {exc}")
    if width < MIN_MAP_WIDTH or height < MIN_MAP_HEIGHT:
        return AssetValidation(False, str(candidate), width=width, height=height, bytes=size, error="resolution trop faible")
    return AssetValidation(True, str(candidate), width=width, height=height, bytes=size)


def stage_candidate_asset(
    source_path: Path | str,
    asset: ExpectedWorldAsset,
    source_name: str,
    *,
    crop_box: Any = None,
    archive_member: str = "",
) -> RecoveryResult:
    source = Path(source_path)
    source_validation = validate_recovered_asset(source)
    if not source_validation.ok:
        return RecoveryResult(
            source_name,
            asset.key,
            "invalid",
            source_validation.error,
            source_path=str(source),
            bytes=source_validation.bytes,
            archive_member=archive_member,
        )

    candidate_path = CANDIDATE_DIR / f"{asset.key}_{source_name}.png"
    preview_path = PREVIEW_DIR / f"{asset.key}_{source_name}_preview.jpg"
    try:
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            output = image.convert("RGB")
            if crop_box:
                output = output.crop(tuple(int(value) for value in crop_box))
            output.save(candidate_path, "PNG", optimize=True)
            preview = output.copy()
            preview.thumbnail((900, 620))
            preview.save(preview_path, "JPEG", quality=88, optimize=True)
    except (OSError, ValueError) as exc:
        return RecoveryResult(
            source_name,
            asset.key,
            "candidate_failed",
            f"impossible de generer le candidat: {exc}",
            source_path=str(source),
            archive_member=archive_member,
        )

    validation = validate_recovered_asset(candidate_path)
    if not validation.ok:
        return RecoveryResult(
            source_name,
            asset.key,
            "invalid_candidate",
            validation.error,
            source_path=str(source),
            destination_path=str(candidate_path),
            archive_member=archive_member,
            preview_path=str(preview_path),
            bytes=validation.bytes,
        )
    return RecoveryResult(
        source_name,
        asset.key,
        "candidate_requires_validation",
        "Candidat Dofus 3 / Unity extrait. Copie finale bloquee tant que la validation visuelle/humaine n'est pas faite.",
        source_path=str(source),
        destination_path=str(candidate_path),
        width=validation.width,
        height=validation.height,
        bytes=validation.bytes,
        archive_member=archive_member,
        preview_path=str(preview_path),
        requires_human_validation=True,
    )


def copy_asset_to_expected_path(
    source_path: Path | str,
    asset: ExpectedWorldAsset,
    source_name: str,
    *,
    crop_box: Any = None,
) -> RecoveryResult:
    if source_name == "dofus_discovery":
        return RecoveryResult(
            source_name,
            asset.key,
            "rejected",
            REJECTED_DOFUS_DISCOVERY_REASON,
            source_path=str(source_path),
            destination_path=str(asset.destination),
            requires_human_validation=True,
        )
    source = Path(source_path)
    source_validation = validate_recovered_asset(source)
    if not source_validation.ok:
        return RecoveryResult(
            source_name,
            asset.key,
            "invalid",
            source_validation.error,
            source_path=str(source),
            destination_path=str(asset.destination),
            bytes=source_validation.bytes,
        )
    try:
        asset.destination.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            output = image.convert("RGB")
            if crop_box:
                output = output.crop(tuple(int(value) for value in crop_box))
            output.save(asset.destination, "PNG", optimize=True)
    except (OSError, ValueError) as exc:
        return RecoveryResult(
            source_name,
            asset.key,
            "copy_failed",
            f"chemin destination impossible a ecrire: {exc}",
            source_path=str(source),
            destination_path=str(asset.destination),
        )

    validation = validate_recovered_asset(asset.destination)
    if not validation.ok:
        return RecoveryResult(
            source_name,
            asset.key,
            "invalid_output",
            validation.error,
            source_path=str(source),
            destination_path=str(asset.destination),
            bytes=validation.bytes,
        )
    LOGGER.info(
        "[ScanMonde] asset cartographie recupere source=%s source_path=%s destination=%s dimensions=%sx%s bytes=%s",
        source_name,
        source,
        asset.destination,
        validation.width,
        validation.height,
        validation.bytes,
    )
    return RecoveryResult(
        source_name,
        asset.key,
        "copied",
        "Asset valide copie vers le chemin attendu.",
        source_path=str(source),
        destination_path=str(asset.destination),
        width=validation.width,
        height=validation.height,
        bytes=validation.bytes,
    )


def scan_local_image_candidates(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config = config or load_sources_config()
    local_cfg = config.get("local_scan") or {}
    roots = local_cfg.get("roots") or ["."]
    ignore_parts = tuple(normalize_path_part(part) for part in (local_cfg.get("ignore_path_parts") or []))
    candidates: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for root_text in roots:
        root = resolve_project_path(str(root_text))
        if not root.exists():
            continue
        if root.is_file():
            paths = [root]
        else:
            paths = root.rglob("*")
        for path in paths:
            if not path.is_file() or path.suffix.casefold() not in IMAGE_EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            lowered = normalize_path_part(str(resolved))
            if any(part and part in lowered for part in ignore_parts):
                continue
            validation = validate_recovered_asset(resolved)
            if not validation.ok:
                continue
            score = local_candidate_score(resolved)
            if score <= 0:
                continue
            candidates.append(
                {
                    "path": str(resolved),
                    "width": validation.width,
                    "height": validation.height,
                    "bytes": validation.bytes,
                    "score": score,
                }
            )
    return sorted(candidates, key=lambda row: (-int(row["score"]), -int(row["bytes"]), str(row["path"]).casefold()))


def first_local_match(asset: ExpectedWorldAsset, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    aliases = tuple(normalize_text(alias) for alias in asset.aliases)
    for candidate in candidates:
        haystack = normalize_text(str(candidate["path"]))
        if any(alias and alias in haystack for alias in aliases):
            return candidate
    return None


def local_candidate_score(path: Path) -> int:
    haystack = normalize_text(str(path))
    score = 0
    for keyword in ("world", "map", "cartography", "background", "atlas", "amakna", "enutrosor", "enurado"):
        if keyword in haystack:
            score += 3
    for preferred_part in ("cartography", "dofus_maps", "map_assets", "d2data", "backup", "old", "archive"):
        if preferred_part in haystack:
            score += 1
    for bad_word in ("logo", "button", "avatar", "icon", "classe", "resource", "item"):
        if bad_word in haystack:
            score -= 4
    return score


def check_doduda_release_archive(
    missing: Iterable[ExpectedWorldAsset],
    source: dict[str, Any],
    *,
    allow_large_downloads: bool,
) -> list[RecoveryResult]:
    api_url = str(source.get("release_api") or "")
    archive_name = str(source.get("worldmap_archive_name") or "worldmap_images.tar.gz")
    max_bytes = int(source.get("max_auto_download_bytes") or 0)
    if not api_url:
        return [RecoveryResult("doduda", "", "not_configured", "Aucune release_api doduda configuree.")]
    try:
        release = read_json_url(api_url)
    except OSError as exc:
        return [RecoveryResult("doduda", "", "network_failed", f"reseau indisponible: {exc}")]
    asset = next((row for row in release.get("assets", []) if row.get("name") == archive_name), None)
    if not asset:
        return [RecoveryResult("doduda", "", "not_found", f"Archive {archive_name} absente de la release.")]
    size = int(asset.get("size") or 0)
    url = str(asset.get("browser_download_url") or "")
    results = [
        RecoveryResult(
            "doduda",
            "",
            "archive_available",
            f"{archive_name} disponible: {size} octets.",
            source_path=url,
            bytes=size,
        )
    ]
    if size > max_bytes and not allow_large_downloads:
        return results + [
            RecoveryResult(
                "doduda",
                "",
                "large_archive_skipped",
                f"{archive_name} disponible ({size} octets) mais ignore sans --allow-large-downloads.",
                source_path=url,
                bytes=size,
            )
        ]
    archive_path = MAP_RAW_DIR / "doduda" / archive_name
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        free_bytes = shutil.disk_usage(archive_path.parent).free
    except OSError as exc:
        return [RecoveryResult("doduda", "", "disk_check_failed", f"verification espace disque impossible: {exc}")]
    required_bytes = int(size * 1.15) if size else 0
    if size and free_bytes < required_bytes:
        return [
            RecoveryResult(
                "doduda",
                "",
                "insufficient_disk_space",
                f"espace disque insuffisant: libre={free_bytes} requis={required_bytes} archive={size}",
                source_path=url,
                bytes=size,
            )
        ]
    archive_ready = False
    if archive_path.exists() and archive_path.is_file():
        try:
            archive_ready = size == 0 or archive_path.stat().st_size >= size
        except OSError:
            archive_ready = False
    if archive_ready:
        results.append(
            RecoveryResult(
                "doduda",
                "",
                "archive_cached",
                f"Archive locale reutilisee: {archive_path}",
                source_path=str(archive_path),
                bytes=archive_path.stat().st_size,
            )
        )
    else:
        try:
            download_file(url, archive_path)
        except OSError as exc:
            return results + [RecoveryResult("doduda", "", "download_failed", str(exc), source_path=url)]
    return results + extract_matching_worldmap_archive(archive_path, missing)


def extract_matching_worldmap_archive(archive_path: Path, missing: Iterable[ExpectedWorldAsset]) -> list[RecoveryResult]:
    results: list[RecoveryResult] = []
    target_dir = MAP_RAW_DIR / "doduda" / "worldmap_images"
    target_dir.mkdir(parents=True, exist_ok=True)
    pending = {asset.key: asset for asset in missing}
    try:
        with tarfile.open(archive_path, "r|gz") as archive:
            for member in archive:
                if not member.isfile() or Path(member.name).suffix.casefold() not in IMAGE_EXTENSIONS:
                    continue
                asset = matching_asset_for_archive_member(member.name, pending.values())
                if asset is None:
                    continue
                output_path = safe_extract_member(archive, member, target_dir)
                results.append(
                    stage_candidate_asset(
                        output_path,
                        asset,
                        "doduda",
                        archive_member=member.name,
                    )
                )
                pending.pop(asset.key, None)
                if not pending:
                    break
    except (tarfile.TarError, OSError) as exc:
        return [RecoveryResult("doduda", "", "archive_failed", f"Archive doduda invalide: {exc}", source_path=str(archive_path))]
    for asset in pending.values():
        results.append(RecoveryResult("doduda", asset.key, "not_found", "Aucun fichier image correspondant dans l'archive."))
    return results


def matching_asset_for_archive_member(member_name: str, assets: Iterable[ExpectedWorldAsset]) -> ExpectedWorldAsset | None:
    normalized = normalize_text(member_name)
    stem = Path(member_name).stem.casefold()
    normalized_stem = stem.replace("worldmap_", "").replace("world_map_", "").replace("map_", "")
    for asset in assets:
        aliases = tuple(normalize_text(alias) for alias in asset.aliases)
        if any(alias and alias in normalized for alias in aliases):
            return asset
        if any(
            worldmap_id and normalized_stem == str(worldmap_id).casefold()
            for worldmap_id in asset.worldmap_ids
        ):
            return asset
    return None


def safe_extract_member(archive: tarfile.TarFile, member: tarfile.TarInfo, target_dir: Path) -> Path:
    safe_name = Path(member.name).name
    output_path = target_dir / safe_name
    fileobj = archive.extractfile(member)
    if fileobj is None:
        raise OSError(f"membre illisible: {member.name}")
    with fileobj, output_path.open("wb") as handle:
        shutil.copyfileobj(fileobj, handle)
    return output_path


def verify_map_views_paths() -> dict[str, Any]:
    if not MAP_VIEWS_PATH.exists():
        return {"ok": False, "error": "map_views.json absent"}
    try:
        payload = json.loads(MAP_VIEWS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"map_views.json invalide: {exc}"}
    views = payload.get("views") if isinstance(payload, dict) else payload
    if not isinstance(views, list):
        return {"ok": False, "error": "format map_views.json inattendu"}
    result: dict[str, Any] = {"ok": True, "views": {}}
    for asset in expected_world_assets():
        view = next((row for row in views if isinstance(row, dict) and row.get("view_key") == asset.view_key), None)
        actual = str((view or {}).get("asset_path") or (view or {}).get("image_path") or "")
        result["views"][asset.view_key] = {
            "exists": view is not None,
            "expected_asset_path": asset.asset_path,
            "actual_asset_path": actual,
            "matches_expected": actual == asset.asset_path,
        }
    return result


def write_recovery_report(report: RecoveryReport) -> Path:
    report_path = DATA_DIR / "reports" / "cartography_asset_recovery_report.json"
    write_json(report_path, report.to_dict())
    return report_path


def download_file(url: str, destination: Path) -> None:
    if not url:
        raise OSError("URL vide")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    except urllib.error.URLError as exc:
        raise OSError(exc) from exc


def read_json_url(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise OSError(exc) from exc


def run_recovery_commands(executable: str, raw_argument_sets: Any) -> tuple[int, str]:
    """Run only the already-resolved doduda executable, never a command shell.

    Configuration may provide ``command_args`` as a list of argument lists, for
    example ``[[], ["map"]]``. The executable itself is not configurable here;
    it comes from ``find_doduda_executable``. Shell metacharacters are rejected
    even though ``shell=False`` would already treat them as plain arguments.
    """
    argument_sets = raw_argument_sets if isinstance(raw_argument_sets, list) else [[], ["map"]]
    normalized_sets: list[list[str]] = []
    for raw_args in argument_sets:
        if not isinstance(raw_args, list):
            return 1, "configuration doduda invalide: command_args doit contenir des listes d'arguments"
        args = [str(value).strip() for value in raw_args if str(value).strip()]
        if any(value in _FORBIDDEN_COMMAND_TOKENS for value in args):
            return 1, "configuration doduda refusee: operateur shell interdit"
        normalized_sets.append(args)
    if not normalized_sets:
        return 1, "configuration doduda invalide: aucune commande configuree"

    output_parts: list[str] = []
    for args in normalized_sets:
        try:
            completed = subprocess.run(
                [executable, *args],
                cwd=ROOT_DIR,
                shell=False,
                text=True,
                capture_output=True,
                timeout=60 * 30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 1, f"commande doduda echouee: {exc}"
        command_output = "\n".join(
            part for part in (completed.stdout.strip(), completed.stderr.strip()) if part
        )
        if command_output:
            output_parts.append(command_output)
        if completed.returncode != 0:
            output = "\n".join(output_parts)
            return completed.returncode, output[-2000:] if output else "commande doduda echouee sans sortie"

    output = "\n".join(output_parts)
    return 0, output[-2000:] if output else "commandes doduda terminees sans sortie"


def resolve_project_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return ROOT_DIR / path


def normalize_text(text: str) -> str:
    return (
        text.replace("\\", "/")
        .replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("ë", "e")
        .replace("É", "e")
        .replace("ï", "i")
        .replace("î", "i")
        .replace("ô", "o")
        .replace("ö", "o")
        .replace("û", "u")
        .replace("ù", "u")
        .replace("à", "a")
        .replace("â", "a")
        .casefold()
    )


def normalize_path_part(text: str) -> str:
    return normalize_text(str(resolve_project_path(text) if not Path(text).is_absolute() else text))
