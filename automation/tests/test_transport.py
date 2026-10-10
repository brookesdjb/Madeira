import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import pytest
from automation.controller.device import AutomationError
from automation.controller.transport import CommandTransport, validate_endpoint
from automation.controller.game_control import command
from automation.controller.jit_probe import snapshot

ROOT = Path(__file__).resolve().parents[2]
TOKEN = 'a' * 72

@pytest.mark.parametrize('change', [{'pid': 43}, {'pid': True}, {'port': 0}, {'token': 'short'}])
def test_stale_or_invalid_endpoint(change):
    value = dict(schema_version=1, pid=42, port=12345, token=TOKEN)
    value.update(change)
    with pytest.raises(AutomationError): validate_endpoint(value, 42)

@pytest.mark.parametrize('reply', [b'', b'{}\n', b'{"pid":42,"schema_version":2,"request_id":"wrong","status":"completed"}\n', b'x' * 65537])
def test_failed_delivery_never_retries_through_UI(reply):
    left, right = socket.socketpair()
    def server():
        with right:
            right.recv(8192)
            try: right.sendall(reply)
            except BrokenPipeError: pass
    thread = threading.Thread(target=server); thread.start()
    d = SimpleNamespace(command_transport=CommandTransport(left, TOKEN, 42))
    with pytest.raises(AutomationError, match='may_have_run'):
        command(d, 'get_status', reply_timeout=1)
    with pytest.raises(AutomationError, match='closed_no_UI'):
        command(d, 'get_status')
    thread.join(timeout=2)
    assert not thread.is_alive()

@pytest.fixture(scope='module')
def native_binary(tmp_path_factory):
    if sys.platform != 'darwin' or not shutil.which('swiftc'):
        pytest.skip('actual Network.framework listener requires macOS Swift')
    binary = tmp_path_factory.mktemp('transport-build') / 'listener'
    subprocess.run(['swiftc', '-DDEBUG', '-DMADEIRA_AUTOMATION',
        str(ROOT/'app/Madeira/AutomationTransport.swift'),
        str(ROOT/'automation/tests/fixtures/transport_host.swift'), '-o', str(binary)], check=True, capture_output=True)
    return binary

@pytest.fixture
def listener(native_binary, tmp_path):
    endpoint = tmp_path / 'endpoint.json'
    proc = subprocess.Popen([str(native_binary), str(endpoint)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        until = time.monotonic() + 5
        while not endpoint.exists():
            assert proc.poll() is None
            assert time.monotonic() < until
            time.sleep(0.02)
        config = validate_endpoint(json.loads(endpoint.read_text()), proc.pid)
        assert endpoint.stat().st_mode & 0o777 == 0o600
        yield config
    finally:
        proc.terminate(); proc.wait(timeout=5)


def connect(config):
    return socket.create_connection(('127.0.0.1', config['port']), timeout=2)


def test_actual_swift_stream_and_no_UI_heartbeat(listener):
    client = CommandTransport(connect(listener), listener['token'], listener['pid'])
    d = SimpleNamespace(command_transport=client)
    try:
        assert command(d, 'get_status')['status'] == 'completed'
        first = snapshot(d)['sequence']
        # Snapshot/heartbeat bypasses the bounded mutation-ID ledger.
        for _ in range(1100): result = snapshot(d)
        assert result['sequence'] == first + 1100
    finally: client.close()


def test_fragmented_frame_and_disconnect_releases_input(listener):
    stream = connect(listener)
    payload = json.dumps({'token':listener['token'], 'kind':'snapshot'}).encode() + b'\n'
    for start in range(0, len(payload), 7): stream.sendall(payload[start:start+7])
    reply = stream.makefile('rb')
    assert json.loads(reply.readline())['replay']['state'] == 'RUNNING'
    reply.close(); stream.close()
    time.sleep(0.05)
    client = CommandTransport(connect(listener), listener['token'], listener['pid'])
    try: assert client.snapshot()['replay']['state'] == 'TRANSPORT_DISCONNECTED'
    finally: client.close()

@pytest.mark.parametrize('payload', [b'{"token":"wrong","kind":"snapshot"}\n', b'x' * 8193])
def test_unauthenticated_or_oversize_does_not_control_replay(listener, payload):
    with connect(listener) as stream:
        stream.sendall(payload)
        assert stream.recv(1) == b''
    client = CommandTransport(connect(listener), listener['token'], listener['pid'])
    try: assert client.snapshot()['replay']['state'] == 'RUNNING'
    finally: client.close()


def test_second_controller_cannot_take_over(listener):
    client = CommandTransport(connect(listener), listener['token'], listener['pid'])
    try:
        client.snapshot()
        with connect(listener) as other:
            assert other.recv(1) == b''
        assert client.snapshot()['replay']['state'] == 'RUNNING'
    finally: client.close()


def test_partial_unauthenticated_request_expires(listener):
    with connect(listener) as stream:
        stream.settimeout(7)
        stream.sendall(b'{')
        assert stream.recv(1) == b''
    client = CommandTransport(connect(listener), listener['token'], listener['pid'])
    try: assert client.snapshot()['replay']['state'] == 'RUNNING'
    finally: client.close()


@pytest.mark.parametrize('route, flag', [('usb', '-l'), ('wifi', '-n')])
def test_attachment_routes_and_cleans_up_after_failure(monkeypatch, route, flag):
    from automation.controller.transport import attach_transport
    left, right = socket.socketpair()
    def server():
        with right:
            assert json.loads(right.recv(8192))['kind'] == 'snapshot'
            right.sendall(b'{"pid":42,"schema_version":1,"sequence":1}\n')
    thread = threading.Thread(target=server); thread.start()
    calls = []
    class Native:
        copied = None
        def command(self, argv, timeout):
            self.copied = Path(argv[argv.index('--destination') + 1])
            assert self.copied.parent.stat().st_mode & 0o077 == 0
            self.copied.write_text(json.dumps(dict(schema_version=1, pid=42, port=12345, token=TOKEN)))
    class Proxy:
        ended = False
        def poll(self): return None
        def terminate(self): self.ended = True
        def wait(self, timeout): return 0
    proxy = Proxy()
    def popen(argv, **kwargs): calls.append(argv); return proxy
    monkeypatch.setattr('automation.controller.transport.subprocess.Popen', popen)
    monkeypatch.setattr('automation.controller.transport.socket.create_connection', lambda *a, **kw: left)
    device, native = SimpleNamespace(), Native()
    with pytest.raises(RuntimeError, match='test_failure'):
        with attach_transport(device, native, 'test-device', 'test.bundle', 42, route=route) as client:
            assert device.command_transport is client
            raise RuntimeError('test_failure')
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert proxy.ended and client.closed and device.command_transport is None
    assert not native.copied.exists()
    assert flag in calls[0] and calls[0][calls[0].index('-s') + 1] == '127.0.0.1'
