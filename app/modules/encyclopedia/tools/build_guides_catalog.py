from __future__ import annotations

import argparse
import sys

from app.modules.encyclopedia.services.guide_catalog_builder import GuideCatalogBuilder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Construit ou vérifie le catalogue local des guides Encyclopédie.")
    parser.add_argument("--check", action="store_true", help="Vérifie les parcours détectables sans écrire de fichier.")
    parser.add_argument("--report", action="store_true", help="Écrit artifacts/guides_build_report.json.")
    parser.add_argument("--write-missing", action="store_true", help="Écrit uniquement les guides absents et met à jour catalog.json avec sauvegarde.")
    parser.add_argument("--write-audited", action="store_true", help="Écrit les Guides explicitement audités par l'addendum et le catalogue.")
    args = parser.parse_args(argv)

    builder = GuideCatalogBuilder()
    result = builder.build()
    active = [row for row in result.catalog.get("guides", []) if row.get("enabled")]
    dofus_added = result.report.get("guides_dofus_ajoutes", [])
    refused = result.report.get("guides_non_ajoutes", [])

    print(f"Categories: {', '.join(result.report.get('categories', []))}")
    print(f"Guides actifs detectes: {len(active)}")
    print(f"Guides Dofus constructibles: {len(dofus_added)}")
    print(f"Guides Dofus non ajoutes: {len(refused)}")

    if args.write_missing:
        written = builder.write_missing(result)
        print(f"Fichiers ecrits: {len(written)}")
        for path in written:
            print(f"WRITE: {path}")
    elif args.write_audited:
        written = builder.write_audited(result)
        print(f"Fichiers audites ecrits: {len(written)}")
        for path in written:
            print(f"WRITE: {path}")
    else:
        print("Mode lecture seule: aucune ecriture de guide.")

    if args.report:
        report_path = builder.write_report(result)
        print(f"Rapport: {report_path}")

    if args.check:
        blocking = [entry for entry in refused if entry.get("raison_refus") not in {"aucune quête fiable liée au succès récompensant l'objet", "aucun succès fiable récompensant l'objet"}]
        if blocking:
            for entry in blocking:
                print(f"ERROR: {entry.get('nom')}: {entry.get('raison_refus')}")
            return 1
        print("Check OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
