"""One host-wide physical-device lease, shared by all Madeira worktrees.

The lock file is never unlinked: replacing it would let clients lock different
inodes. The kernel releases the lease when its owning process exits.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import uuid

from .device import AutomationError


def reservation_path(udid, root=None):
    if not isinstance(udid, str) or not udid:
        raise AutomationError("reservation_requires_hardware_udid")
    # Do not expose hardware identifiers in filenames or public reports.
    key = hashlib.sha256(udid.encode()).hexdigest()
    directory = Path(root or os.getenv("MADEIRA_RESERVATION_DIR") or
                     Path.home() / ".local/state/madeira/device-reservations")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory / (key + ".lock")


@contextmanager
def reserve_device(udid, owner, run_id=None, root=None):
    path = reservation_path(udid, root)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    acquired = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError:
            raise AutomationError("device_reserved_by_another_run") from None
        previous = os.read(fd, 16_384)
        try:
            stale = json.loads(previous).get("state") == "held"
        except (ValueError, AttributeError):
            stale = False
        # Kernel ownership is authoritative; metadata/PIDs never permit stealing
        # a live lock. A held record with an acquired lock is an exited owner.
        metadata = {"schema_version": 1, "state": "held", "owner": owner,
                    "run_id": run_id or uuid.uuid4().hex, "pid": os.getpid(),
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "recovered_exited_owner": stale}
        def write(value):
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, json.dumps(value).encode())
            os.fsync(fd)
        write(metadata)
        try:
            yield dict(metadata)
        finally:
            write({**metadata, "state": "released",
                   "finished_at": datetime.now(timezone.utc).isoformat()})
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
