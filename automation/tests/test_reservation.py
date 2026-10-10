import json
import multiprocessing
from pathlib import Path
import subprocess
import sys

import pytest

from automation.controller.device import AutomationError
from automation.controller.reservation import reservation_path, reserve_device


def competing_client(root, connection):
    try:
        with reserve_device("tablet", "second", root=root):
            connection.send("acquired")
    except AutomationError as exc:
        connection.send(str(exc))
    finally:
        connection.close()


def test_an_independent_process_cannot_steal_live_reservation(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe()
    with reserve_device("tablet", "first", root=tmp_path):
        process = ctx.Process(target=competing_client, args=(tmp_path, child))
        process.start()
        assert parent.poll(10)
        assert parent.recv() == "device_reserved_by_another_run"
        process.join(10)
        assert process.exitcode == 0
    with reserve_device("tablet", "next", root=tmp_path) as lease:
        assert lease["recovered_exited_owner"] is False


def test_exception_releases_without_replacing_lock_inode(tmp_path):
    path = reservation_path("tablet", tmp_path)
    with pytest.raises(RuntimeError):
        with reserve_device("tablet", "failure", root=tmp_path):
            inode = path.stat().st_ino
            raise RuntimeError("failure")
    with reserve_device("tablet", "retry", root=tmp_path):
        assert path.stat().st_ino == inode
    assert json.loads(path.read_text())["state"] == "released"
    assert path.stat().st_mode & 0o077 == 0


def test_abrupt_process_death_is_recovered_by_kernel_lock(tmp_path):
    code = '''import sys,time
from automation.controller.reservation import reserve_device
with reserve_device("tablet", "crash", root=sys.argv[1]):
    print("held", flush=True)
    time.sleep(30)
'''
    process = subprocess.Popen([sys.executable, "-c", code, str(tmp_path)],
                               stdout=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == "held"
        with pytest.raises(AutomationError, match="reserved"):
            with reserve_device("tablet", "competitor", root=tmp_path):
                pytest.fail("stole live reservation")
    finally:
        process.kill()
        process.wait(timeout=10)
    with reserve_device("tablet", "recovery", root=tmp_path) as lease:
        assert lease["recovered_exited_owner"] is True


def test_device_keys_are_private_and_distinct(tmp_path):
    assert reservation_path("private-device-one", tmp_path) != reservation_path("private-device-two", tmp_path)
    assert "private-device" not in str(reservation_path("private-device-one", tmp_path))
