"""Import the official IBGE boundaries of Ceará (state + 184 municipalities).

    python -m seed.jurisdictions                # import / confirm (idempotent)
    python -m seed.jurisdictions --verify-files # only check the SHA-256 of the files

Unlike the demo seed this runs in every environment, staging and production
included: it loads published official data, never demonstration records. The
container's migrate role runs it right after `alembic upgrade head`.
"""

import argparse
import asyncio
import sys
from pathlib import Path


async def _import(dataset_dir: Path) -> int:
    import app.main  # noqa: F401 — registers every ORM mapper (audit_logs → users)
    from app.database import AsyncSessionLocal, engine
    from app.geo.ibge_import import import_state

    try:
        async with AsyncSessionLocal() as session:
            report = await import_state(session, dataset_dir)
            await session.commit()
    finally:
        await engine.dispose()
    print(
        "==> Jurisdições IBGE: "
        f"{report.municipalities} municípios no arquivo; inseridas {report.inserted}, "
        f"atualizadas {report.updated}, sem alteração {report.unchanged} "
        f"(dataset {report.dataset_id}{', novo' if report.dataset_created else ''})."
    )
    if report.not_in_dataset:
        print(f"    Aviso: municípios no banco ausentes desta malha: {report.not_in_dataset}")
    return 0


def main(argv: list[str]) -> int:
    from app.geo.ibge_import import (
        DEFAULT_DATASET_DIR,
        DatasetIntegrityError,
        load_manifest,
        verify_files,
    )

    parser = argparse.ArgumentParser(prog="python -m seed.jurisdictions")
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--verify-files", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.verify_files:
            manifest = load_manifest(args.dataset_dir)
            verify_files(manifest)
            print(f"==> Arquivos conferem com {manifest.path} (sha256 {manifest.content_sha256}).")
            return 0
        return asyncio.run(_import(args.dataset_dir))
    except DatasetIntegrityError as exc:
        print(f"Recusado: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
