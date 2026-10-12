"""Publish complete observer events without sharing an append/rotation lock."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_writer_id = uuid.uuid4().hex
_writer_pid = os.getpid()
_sequence = 0
_last_created_ns = 0


def _after_fork() -> None:
    # A fork can inherit a mutex held by a thread that does not exist in the
    # child. Allocate both the process identity and its lock afresh.
    global _lock, _writer_id, _writer_pid, _sequence, _last_created_ns
    _lock = threading.Lock()
    _writer_id = uuid.uuid4().hex
    _writer_pid = os.getpid()
    _sequence = _last_created_ns = 0


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


def read_epoch(directory: Path) -> str:
    """Read either the initial plaintext epoch or an authoritative reset intent."""
    try:
        raw = (Path(directory) / "event-epoch").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "initial"
    if not raw.startswith("{"):
        return raw or "initial"
    intent = json.loads(raw)
    if (intent.get("version") != 1 or intent.get("reset") is not True
            or not isinstance(intent.get("epoch"), str) or not intent["epoch"]):
        raise ValueError("invalid office reset intent")
    return intent["epoch"]


def publish(directory: Path, event: dict[str, Any]) -> Path:
    """Atomically publish one envelope; callers decide how to report IO errors.

    Receipt identity belongs to this publication, not to its payload or event
    timestamp. Identical payloads are separate events. Ready names are never
    reused; a consumer may safely remove a file after its transaction commits.
    """
    global _writer_id, _writer_pid, _sequence, _last_created_ns
    directory = Path(directory)
    inbox = directory / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    with _lock:
        if _writer_pid != os.getpid():
            _writer_pid = os.getpid()
            _writer_id = uuid.uuid4().hex
            _sequence = _last_created_ns = 0
        epoch = read_epoch(directory)
        created_ns = max(time.time_ns(), _last_created_ns + 1)
        _last_created_ns = created_ns
        _sequence += 1
        filename = f"{created_ns:020d}-{_writer_id}-{_sequence:012d}.json"
        envelope = {
            "version": 1, "epoch": epoch, "created_ns": str(created_ns),
            "writer_id": _writer_id, "sequence": _sequence, "event": event,
        }
        encoded = json.dumps(envelope, ensure_ascii=False, default=str) + "\n"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=inbox, prefix="." + filename + ".",
                suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            ready = inbox / filename
            temporary.replace(ready)
            temporary = None
            return ready
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
