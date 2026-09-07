"""CLI d'extraction : exécute une requête SQL et exporte le résultat.

La requête est lue depuis un fichier `.sql`, exécutée par lots pour ne pas
charger un grand résultat en mémoire d'un coup, puis exportée en CSV, Excel
ou Parquet.

Usage :
    python scripts/extract.py --db postgres --query requete.sql \
        --param id:int=42 --output export/donnees --format csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

# `src` n'est importable que si la racine du projet est sur sys.path : ce
# script est lancé directement (`python scripts/extract.py`), pas via `-m`,
# donc seul le dossier scripts/ y est ajouté par défaut.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import DatabaseManager, DatabaseType  # noqa: E402
from src.exceptions import AppError  # noqa: E402
from src.export import ExportFormat, export_batches  # noqa: E402
from src.logging_config import setup_logging  # noqa: E402
from src.settings import AppSettings, load_env  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover - import réservé au typage
    import pandas as pd

logger: Final[logging.Logger] = logging.getLogger(__name__)

_EXIT_OK: Final[int] = 0
_EXIT_FAILURE: Final[int] = 1

_DEFAULT_BATCH_SIZE: Final[int] = 50_000

_PARAM_TYPES: Final[dict[str, type]] = {"str": str, "int": int, "float": float}


def parse_parameter(raw: str) -> tuple[str, str | int | float]:
    """Analyse un paramètre `--param NOM[:TYPE]=VALEUR`.

    Seul le premier `=` sépare le nom (et son type éventuel) de la valeur :
    `filtre=a=b` donne `("filtre", "a=b")`.

    Args:
        raw: Chaîne brute reçue en ligne de commande.

    Returns:
        Un tuple (nom du paramètre, valeur convertie).

    Raises:
        argparse.ArgumentTypeError: Syntaxe invalide, type inconnu, ou valeur
            inconvertible dans le type demandé.
    """
    if "=" not in raw:
        raise argparse.ArgumentTypeError(
            f"Paramètre invalide (attendu NOM[:TYPE]=VALEUR) : {raw!r}"
        )
    name_and_type, _, raw_value = raw.partition("=")
    name, _, type_name = name_and_type.partition(":")
    name = name.strip()
    type_name = type_name.strip() or "str"

    if not name:
        raise argparse.ArgumentTypeError(f"Nom de paramètre vide : {raw!r}")

    converter = _PARAM_TYPES.get(type_name)
    if converter is None:
        raise argparse.ArgumentTypeError(
            f"Type de paramètre inconnu ({type_name!r}) pour {name!r} : "
            f"attendu {', '.join(_PARAM_TYPES)}"
        )

    try:
        value: str | int | float = converter(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Valeur inconvertible en {type_name} pour {name!r} : {raw_value!r}"
        ) from exc

    return name, value


def read_query(path: Path) -> str:
    """Lit une requête SQL depuis un fichier, sans point-virgule final.

    Args:
        path: Chemin du fichier `.sql`.

    Returns:
        Le texte de la requête, dépouillé et sans point-virgule final.

    Raises:
        AppError: Si le fichier est absent, illisible, ou vide une fois
            dépouillé.
    """
    try:
        content: str = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AppError(f"Requête illisible ({path}) : {exc}") from exc

    query: str = content.strip()
    if query.endswith(";"):
        query = query[:-1].strip()

    if not query:
        raise AppError(f"Requête vide : {path}")

    return query


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Analyse les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(
        prog="python scripts/extract.py",
        description="Exécute une requête SQL et exporte le résultat en fichier.",
    )
    parser.add_argument(
        "--db",
        choices=[db.value for db in DatabaseType],
        required=True,
        help="Moteur cible.",
    )
    parser.add_argument(
        "--query",
        type=Path,
        required=True,
        help="Chemin du fichier .sql contenant la requête.",
    )
    parser.add_argument(
        "--param",
        dest="params",
        action="append",
        type=parse_parameter,
        default=[],
        metavar="NOM[:TYPE]=VALEUR",
        help="Paramètre nommé (répétable). Types : str (défaut), int, float.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Chemin de sortie (extension ajoutée ou corrigée selon --format).",
    )
    parser.add_argument(
        "--format",
        choices=[fmt.value for fmt in ExportFormat],
        default=ExportFormat.CSV.value,
        help="Format d'export (défaut : csv).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=_DEFAULT_BATCH_SIZE,
        help=f"Nombre de lignes par lot lu (défaut : {_DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Chemin d'un fichier de log rotatif (optionnel).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Exécute l'extraction : lecture de la requête, requêtage, export.

    Les valeurs des paramètres ne sont jamais journalisées (potentiellement
    sensibles) ; seuls leurs noms le sont.

    Returns:
        0 si l'export a réussi, 1 sinon.
    """
    args: argparse.Namespace = parse_args(argv)

    load_env()
    app: AppSettings = AppSettings.from_env()
    setup_logging(app.log_level, log_file=args.log_file)

    db_type: DatabaseType = DatabaseType(args.db)
    export_format: ExportFormat = ExportFormat(args.format)
    params: dict[str, str | int | float] = dict(args.params)

    logger.info(
        "Extraction %s -> %s (format=%s, lots=%d, paramètres=%s)",
        db_type.value,
        args.output,
        export_format.value,
        args.batch_size,
        ", ".join(sorted(params)) or "aucun",
    )

    try:
        query: str = read_query(args.query)
    except AppError as exc:
        logger.error("Lecture de la requête impossible : %s", exc)
        return _EXIT_FAILURE

    try:
        with DatabaseManager.from_env() as manager:
            batches: Iterator["pd.DataFrame"] = manager.iter_dataframes(
                db_type, query, params, batch_size=args.batch_size
            )
            output_path, row_count = export_batches(batches, args.output, export_format)
    except (AppError, ValueError) as exc:
        logger.error("Extraction en échec : %s", exc)
        return _EXIT_FAILURE

    logger.info("Export terminé : %s (%d ligne(s))", output_path, row_count)
    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
