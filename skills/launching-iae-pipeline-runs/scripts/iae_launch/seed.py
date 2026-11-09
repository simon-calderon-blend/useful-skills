"""Siembra en S3: puts de archivos locales y copias server-side."""

from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from typing import Any, Callable, Literal

_CONTENT_TYPES = {".pdf": "application/pdf", ".json": "application/json",
                  ".xml": "application/xml"}


@dataclass(frozen=True)
class SeedItem:
    kind: Literal["put", "copy"]
    source: str            # ruta local (put) o s3://bucket/key (copy)
    dest_suffix: str       # relativo a <base>/<process_id>/
    content_type: str


def content_type_for(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    return _CONTENT_TYPES.get(ext) or mimetypes.guess_type(name)[0] or "application/octet-stream"


def parse_s3_uri(uri: str) -> tuple[str, str]:
    bucket, _, key = uri.removeprefix("s3://").partition("/")
    return bucket, key


MAX_COPY_BYTES = 5 * 1024 ** 3


def check_copy_size(name: str, size: int) -> None:
    """copy_object no admite objetos > 5 GB: se falla claro al planificar."""
    if size > MAX_COPY_BYTES:
        raise ValueError(f"{name}: {size} bytes > 5 GB, no se puede copiar server-side")


def seed_items(s3: Any, bucket: str, base_prefix: str, process_id: str,
               items: list[SeedItem], on_item: Callable[[str], None] | None = None) -> list[str]:
    """Siembra ``items`` bajo ``<base>/<pid>/``; omite ocultos. Devuelve las keys escritas."""
    written: list[str] = []
    for item in items:
        # Ocultos: solo se omiten los locales (basura del SO); una copia desde un pid previo
        # conserva p. ej. .ingestion-meta.json (secuencia probada en un lanzamiento real).
        if item.kind == "put" and os.path.basename(item.dest_suffix).startswith("."):
            continue
        key = f"{base_prefix}/{process_id}/{item.dest_suffix}"
        if item.kind == "put":
            with open(item.source, "rb") as fh:
                s3.put_object(Bucket=bucket, Key=key, Body=fh, ContentType=item.content_type)
        else:
            src_bucket, src_key = parse_s3_uri(item.source)
            extra = ({"ContentType": item.content_type, "MetadataDirective": "REPLACE"}
                     if item.content_type else {"MetadataDirective": "COPY"})
            s3.copy_object(Bucket=bucket, Key=key,
                           CopySource={"Bucket": src_bucket, "Key": src_key}, **extra)
        written.append(key)
        if on_item:
            on_item(key)
    return written
