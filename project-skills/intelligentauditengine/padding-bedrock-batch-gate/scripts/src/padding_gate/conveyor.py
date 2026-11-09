"""Read-only view of the conveyor: depth, PENDING chunks, and which job each would join.

batch-trigger does not build one job from the queue. It drains, resolves each
chunk's frozen run config (run_id -> pointer -> body) and groups the chunks by the
body's model.model_id; a group below min_records_per_job is released for the next
tick (lambda-batch-trigger/index.py, grouping loop). So padding only helps if the
filler resolves to the SAME model as the real chunks it is meant to carry.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

# Pad by the gap plus this: the depth the gate compares against is
# ApproximateNumberOfMessages, and the drain discards duplicates and stale
# messages, so the bare gap can land back under the gate. Same value the
# pipeline_runner conveyor watcher uses.
INJECT_BUFFER = 10


@dataclass(frozen=True)
class QueueDepth:
    visible: int
    inflight: int


@dataclass(frozen=True)
class PendingChunk:
    chunk_id: str
    pdf_id: str
    process_id: str
    run_id: str
    doc_code: str
    spuria_run_id: str | None

    @property
    def is_spuria(self) -> bool:
        return self.spuria_run_id is not None


@dataclass
class ModelGroup:
    model_id: str
    digest: str
    real: int = 0
    spuria: int = 0

    @property
    def total(self) -> int:
        return self.real + self.spuria


def queue_url(sqs: Any, queue_name: str) -> str:
    return sqs.get_queue_url(QueueName=queue_name)["QueueUrl"]


def queue_depth(sqs: Any, url: str) -> QueueDepth:
    attrs = sqs.get_queue_attributes(
        QueueUrl=url,
        AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
    )["Attributes"]
    return QueueDepth(
        visible=int(attrs["ApproximateNumberOfMessages"]),
        inflight=int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0)),
    )


def _s(item: dict, key: str) -> str:
    return item.get(key, {}).get("S", "")


def scan_pending(ddb: Any, table: str) -> list[PendingChunk]:
    """Every chunk row in PENDING, real or filler. Low-level client on purpose:
    rows are compared field by field with what chunk_pdf.py writes."""
    paginator = ddb.get_paginator("scan")
    pages = paginator.paginate(
        TableName=table,
        FilterExpression="#s = :pending",
        ProjectionExpression="chunk_id, pdf_id, process_id, run_id, doc_code, spuria_run_id",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":pending": {"S": "PENDING"}},
    )
    return [
        PendingChunk(
            chunk_id=_s(item, "chunk_id"),
            pdf_id=_s(item, "pdf_id"),
            process_id=_s(item, "process_id"),
            run_id=_s(item, "run_id"),
            doc_code=_s(item, "doc_code"),
            spuria_run_id=_s(item, "spuria_run_id") or None,
        )
        for page in pages
        for item in page.get("Items", [])
    ]


class RunConfigResolver:
    """run_id -> pointer -> body, memoized like shared_extraction_lib.run_config."""

    def __init__(
        self, s3: Any, *, bucket: str, base_prefix: str, pointers_prefix: str, run_configs_prefix: str
    ) -> None:
        self._s3 = s3
        self._bucket = bucket
        self._base = base_prefix.rstrip("/")
        self._pointers = pointers_prefix.strip("/")
        self._bodies_prefix = run_configs_prefix.strip("/")
        self._digests: dict[tuple[str, str], str | None] = {}
        self._bodies: dict[str, dict] = {}

    def pointer_key(self, process_id: str, run_id: str) -> str:
        return f"{self._base}/{process_id}/{self._pointers}/{run_id}.json"

    def _get_json(self, key: str) -> dict | None:
        try:
            raw = self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except self._s3.exceptions.NoSuchKey:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None  # batch-trigger cannot use it either: unresolved

    def digest_for(self, process_id: str, run_id: str) -> str | None:
        key = (process_id, run_id)
        if key not in self._digests:
            pointer = self._get_json(self.pointer_key(process_id, run_id))
            self._digests[key] = (pointer or {}).get("config_digest")
        return self._digests[key]

    def body(self, digest: str) -> dict:
        if digest not in self._bodies:
            self._bodies[digest] = self._get_json(f"{self._base}/{self._bodies_prefix}/{digest}.json") or {}
        return self._bodies[digest]

    def documents(self, digest: str) -> set[str]:
        return set(self.body(digest).get("documents") or {})

    def model_of(self, process_id: str, run_id: str) -> tuple[str, str] | None:
        digest = self.digest_for(process_id, run_id)
        if digest is None:
            return None
        model_id = self.body(digest).get("model", {}).get("model_id")
        return (digest, model_id) if model_id else None


def group_by_model(
    chunks: list[PendingChunk], resolver: RunConfigResolver
) -> tuple[list[ModelGroup], int]:
    """Groups ordered by real chunk count (largest first), plus the unresolvable count."""
    groups: dict[str, ModelGroup] = {}
    digests: dict[str, Counter[str]] = {}
    unresolved = 0
    for chunk in chunks:
        resolved = resolver.model_of(chunk.process_id, chunk.run_id)
        if resolved is None:
            unresolved += 1
            continue
        digest, model_id = resolved
        group = groups.setdefault(model_id, ModelGroup(model_id=model_id, digest=digest))
        if chunk.is_spuria:
            group.spuria += 1
        else:
            group.real += 1
            digests.setdefault(model_id, Counter())[digest] += 1
    for model_id, counter in digests.items():
        # The digest most real chunks of this model froze: the safest one to reuse.
        groups[model_id].digest = counter.most_common(1)[0][0]
    ordered = sorted(groups.values(), key=lambda g: (-g.real, g.model_id))
    return ordered, unresolved


def needed_count(min_records: int, visible: int, group_total: int) -> int:
    """Filler needed for the queue AND the target model group to cross the gate."""
    gap = min_records - min(visible, group_total)
    return gap + INJECT_BUFFER if gap > 0 else 0
