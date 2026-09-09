from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.maps.cartography_asset_recovery import (  # noqa: E402
    recover_missing_cartography_assets,
    scan_existing_cartography_assets,
    verify_map_views_paths,
    write_recovery_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover local Dofus Atlas cartography assets.")
    parser.add_argument(
        "--allow-large-downloads",
        action="store_true",
        help="Allow downloading very large archives such as worldmap_images.tar.gz.",
    )
    parser.add_argument("--no-network", action="store_true", help="Only scan local files.")
    parser.add_argument("--skip-doduda-cli", action="store_true", help="Do not run doduda even if installed.")
    args = parser.parse_args()

    print("== Dofus Atlas cartography asset recovery ==")
    before = scan_existing_cartography_assets()
    print_assets("Assets avant recuperation", before)

    map_views = verify_map_views_paths()
    print("\nmap_views.json:")
    for view_key, row in (map_views.get("views") or {}).items():
        print(
            f"  - {view_key}: exists={row.get('exists')} "
            f"asset_path={row.get('actual_asset_path')} expected={row.get('expected_asset_path')} "
            f"matches={row.get('matches_expected')}"
        )

    report = recover_missing_cartography_assets(
        allow_network=not args.no_network,
        allow_large_downloads=args.allow_large_downloads,
        run_doduda_cli=not args.skip_doduda_cli,
    )
    report_path = write_recovery_report(report)

    print("\nSources testees:")
    for source in report.sources_tested:
        print(f"  - {source}")

    print("\nCandidats locaux retenus:")
    if report.local_candidates:
        for candidate in report.local_candidates[:10]:
            print(
                f"  - {candidate['path']} "
                f"({candidate['width']}x{candidate['height']}, {candidate['bytes']} octets, score={candidate['score']})"
            )
    else:
        print("  Aucun candidat local fiable.")

    print("\nResultats:")
    for result in report.results:
        suffix = ""
        if result.destination_path:
            suffix += f" -> {result.destination_path}"
        if result.width and result.height:
            suffix += f" ({result.width}x{result.height}, {result.bytes} octets)"
        if result.archive_member:
            suffix += f" archive_member={result.archive_member}"
        if result.preview_path:
            suffix += f" preview={result.preview_path}"
        if result.requires_human_validation:
            suffix += " validation_humaine_requise=true"
        print(f"  - [{result.source}] {result.asset_key or '-'} {result.status}: {result.message}{suffix}")

    print("\nRejets connus:")
    if report.rejections:
        for rejection in report.rejections:
            print(
                f"  - {rejection['asset_key']}: exists={rejection['exists']} "
                f"source={rejection['source']} path={rejection['path']} reason={rejection['reason']}"
            )
    else:
        print("  Aucun rejet connu.")

    print_assets("Assets apres recuperation", report.existing_after)
    print(f"\nRapport JSON: {report_path}")
    missing = report.existing_after.get("missing") or []
    if missing:
        print("\nAssets encore manquants:")
        for key in missing:
            print(f"  - {key}")
        print("Impossible de recuperer les cartes : aucune source exploitable trouvee pour les assets restants.")
    else:
        print("\nTous les assets attendus sont presents.")
    return 0


def print_assets(title: str, scan: dict) -> None:
    print(f"\n{title}:")
    for key, row in (scan.get("assets") or {}).items():
        if row.get("exists"):
            print(f"  - {key}: OK {row['width']}x{row['height']} {row['bytes']} octets -> {row['destination']}")
        else:
            print(f"  - {key}: MANQUANT -> {row['destination']} ({row.get('error')})")


if __name__ == "__main__":
    raise SystemExit(main())
