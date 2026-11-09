"""``runs/<run_id>/process_index.csv`` (mismas columnas que el runner)."""

from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path

COLUMNS = ["radicado", "pid", "descargado", "s3uri"]


class RunIndexError(RuntimeError):
    pass


class RunIndex:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.rows: dict[str, dict] = {}
        if self.path.is_file():
            try:
                with self.path.open(newline="", encoding="utf-8") as fh:
                    reader = csv.DictReader(fh)
                    if reader.fieldnames != COLUMNS:
                        raise RunIndexError(f"{self.path}: cabecera {reader.fieldnames} != {COLUMNS}")
                    self.rows = {r["radicado"]: r for r in reader}
            except (csv.Error, UnicodeDecodeError, KeyError) as exc:
                raise RunIndexError(f"{self.path} está mal formado: {exc}") from None

    def record(self, radicado: str, *, pid: str | None = None, descargado: bool | None = None,
               s3uri: str | None = None) -> None:
        row = self.rows.setdefault(radicado, {c: "" for c in COLUMNS})
        row["radicado"] = radicado
        if pid is not None:
            row["pid"] = pid
        if descargado is not None:
            row["descargado"] = "true" if descargado else "false"
        if s3uri is not None:
            row["s3uri"] = s3uri
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".process_index-")
        try:  # temporal + os.replace: un corte no deja el índice a medias
            with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerows(self.rows.values())
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
