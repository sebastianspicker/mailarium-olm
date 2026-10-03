#!/usr/bin/env python3
"""Measure synthetic vector writes, warm queries, and exact duplicate detection."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import random
import statistics
import sys
import tempfile
import time
from contextlib import nullcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _distribution(samples: list[float]) -> dict[str, object]:
    return {
        "seconds": samples,
        "median_seconds": statistics.median(samples),
        "min_seconds": min(samples),
        "max_seconds": max(samples),
    }


def _vector_run(args: argparse.Namespace, *, defer: bool) -> dict[str, object]:
    import numpy as np

    from mailarium.archive import open_archive_database, storage

    rng = np.random.default_rng(args.seed)
    vectors = rng.normal(size=(args.rows, args.dimensions)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    ids = [f"synthetic-{index}__0" for index in range(args.rows)]
    metadata = [{"uid": f"synthetic-{index}"} for index in range(args.rows)]
    documents = ["Synthetic benchmark evidence."] * args.rows
    with tempfile.TemporaryDirectory(prefix="mailarium-benchmark-") as temporary:
        with open_archive_database(str(Path(temporary) / "archive.db")) as db:
            collection = storage.get_vector_collection(
                database=db, vector_index_path=str(Path(temporary) / "vectors"), model_id="synthetic", model_revision="1"
            )
            deferral = getattr(collection, "defer_checkpoints", None)
            context = deferral() if defer and callable(deferral) else nullcontext()
            started = time.perf_counter()
            with context:
                for start in range(0, args.rows, args.batch_size):
                    stop = start + args.batch_size
                    collection.add(
                        ids=ids[start:stop],
                        embeddings=vectors[start:stop],
                        documents=documents[start:stop],
                        metadatas=metadata[start:stop],
                    )
            write_seconds = time.perf_counter() - started
            if collection.count() != args.rows or not collection.verify()["healthy"]:
                raise RuntimeError("synthetic vector persistence or integrity check failed")
            query = vectors[0].tolist()
            if collection.query(query_embeddings=[query], n_results=1)["ids"] != [[ids[0]]]:
                raise RuntimeError("synthetic vector round trip returned the wrong nearest neighbor")
            statements: list[str] = []
            hashes = 0
            original_hash = storage._sha256_file

            def count_hash(path):
                nonlocal hashes
                hashes += 1
                return original_hash(path)

            storage._sha256_file = count_hash
            db.conn.set_trace_callback(statements.append)
            try:
                started = time.perf_counter()
                for _ in range(args.queries):
                    collection.query(query_embeddings=[query], n_results=10)
                query_seconds = time.perf_counter() - started
            finally:
                db.conn.set_trace_callback(None)
                storage._sha256_file = original_hash
                collection.close()
            return {
                "write_seconds": write_seconds,
                "query_seconds": query_seconds,
                "warm_query_sql_statements": len(statements),
                "warm_query_full_file_hashes": hashes,
                "checkpoint_deferral_available": callable(deferral),
            }


def _duplicate_runs(args: argparse.Namespace) -> dict[str, object]:
    from mailarium.investigation.dedup_detector import _build_ngram_cache, _find_matching_pairs

    rng = random.Random(args.seed)
    emails = [(str(index), "".join(rng.choices("abcdefghijklmnopqrstuvwxyz", k=120))) for index in range(args.duplicate_rows)]
    cache = _build_ngram_cache(emails)
    samples = []
    for _ in range(args.repetitions):
        started = time.perf_counter()
        matches = _find_matching_pairs(cache, "Synthetic subject", 0.85, 50)
        samples.append(time.perf_counter() - started)
        if matches:
            raise RuntimeError("synthetic dissimilar bodies unexpectedly matched")
    return {"rows": args.duplicate_rows, "body_characters": 120, "threshold": 0.85, **_distribution(samples)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=2_000)
    parser.add_argument("--dimensions", type=int, default=64)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--queries", type=int, default=10)
    parser.add_argument("--duplicate-rows", type=int, default=800)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    for name in ("rows", "dimensions", "batch_size", "queries", "duplicate_rows", "repetitions"):
        if getattr(args, name) < 1:
            parser.error(f"{name.replace('_', '-')} must be positive")
    output = {
        "schema_version": 1,
        "data": "synthetic seeded vectors and dissimilar email bodies; temporary SQLite and USearch state only",
        "environment": {
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
            "packages": {name: importlib.metadata.version(name) for name in ("numpy", "usearch", "networkx")},
        },
        "parameters": vars(args),
        "vector_runs": {},
    }
    for name, defer in (("immediate", False), ("deferred", True)):
        runs = [_vector_run(args, defer=defer) for _ in range(args.repetitions)]
        output["vector_runs"][name] = {
            "samples": runs,
            "writes": _distribution([float(run["write_seconds"]) for run in runs]),
            "warm_queries": _distribution([float(run["query_seconds"]) for run in runs]),
        }
    output["duplicate_detection"] = _duplicate_runs(args)
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
