"""Bounded request/reply stream over paired USB or Wi-Fi forwarding.

Call attach_transport inside the existing shared device reservation, after launching
an automation-enabled process. Never reconnect/retry a command after uncertain delivery.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
from .device import AutomationError


class CommandTransport:
    def __init__(self, sock, token, pid):
        self.sock, self.token, self.pid = sock, token, pid
        self.closed = False
        self.last_sequence = -1

    def close(self):
        self.closed = True
        self.sock.close()

    def _exchange(self, kind, request=None, timeout=15):
        if self.closed:
            raise AutomationError('transport_closed_no_UI_fallback')
        message = {'token': self.token, 'kind': kind}
        if request is not None:
            message['request'] = request
        payload = json.dumps(message, separators=(',', ':'), allow_nan=False).encode() + b'\n'
        if len(payload) > 8192:
            raise AutomationError('transport_request_too_large')
        deadline = time.monotonic() + timeout
        try:
            self.sock.settimeout(max(0.001, deadline - time.monotonic()))
            self.sock.sendall(payload)
            data = bytearray()
            while b'\n' not in data:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                self.sock.settimeout(remaining)
                chunk = self.sock.recv(min(65537 - len(data), 4096))
                if not chunk or len(data) + len(chunk) > 65536:
                    raise ValueError()
                data.extend(chunk)
            if not data.endswith(b'\n') or data.count(b'\n') != 1:
                raise ValueError()
            result = json.loads(data)
            if not isinstance(result, dict) or type(result.get('pid')) is not int or result['pid'] != self.pid:
                raise ValueError()
            if kind == 'command':
                if (result.get('schema_version') != 2 or result.get('request_id') != request['request_id']
                        or result.get('status') not in {'accepted', 'completed', 'rejected'}):
                    raise ValueError()
            else:
                if (result.get('schema_version') != 1 or type(result.get('sequence')) is not int
                        or result['sequence'] <= self.last_sequence):
                    raise ValueError()
                self.last_sequence = result['sequence']
            return result
        except (OSError, ValueError, TypeError):
            self.close()
            raise AutomationError('transport_failed_request_may_have_run_no_retry') from None

    def command(self, request, timeout=15):
        return self._exchange('command', request, timeout)

    def snapshot(self):
        return self._exchange('snapshot')


def validate_endpoint(value, expected_pid):
    if (not isinstance(value, dict) or value.get('schema_version') != 1
            or type(value.get('pid')) is not int or value['pid'] != expected_pid
            or type(value.get('port')) is not int or not 1 <= value['port'] <= 65535
            or not isinstance(value.get('token'), str)
            or not re.fullmatch(r'[A-Fa-f0-9-]{72}', value['token'])):
        raise AutomationError('invalid_or_stale_transport_endpoint')
    return value


@contextmanager
def attach_transport(device, native, udid, bundle_id, expected_pid, *, route='usb'):
    """Attach within reserve_device; caller must keep the lease for this whole context.

    Snapshot at least every two seconds during a replay (existing benchmark loop
    does this). No background heartbeat: a wedged controller must release input.
    """
    if route not in {'usb', 'wifi'} or type(expected_pid) is not int or expected_pid <= 0:
        raise AutomationError('invalid_transport_configuration')
    if getattr(device, 'command_transport', None) is not None:
        raise AutomationError('transport_already_attached')
    proxy = None
    client = None
    with tempfile.TemporaryDirectory(prefix='madeira-transport-') as directory:
        endpoint = Path(directory) / 'endpoint.private.json'
        try:
            native.command(['device', 'copy', 'from', '--device', udid,
                '--domain-type', 'appDataContainer', '--domain-identifier', bundle_id,
                '--source', 'Documents/automation-transport.private.json', '--destination', str(endpoint)], 30)
            endpoint.chmod(0o600)
            if endpoint.stat().st_size > 1024:
                raise AutomationError('invalid_transport_endpoint_size')
            config = validate_endpoint(json.loads(endpoint.read_text()), expected_pid)
            # iproxy has no dynamic-port reporting. Reserve a candidate, then
            # authenticate the PID/token to reject any bind race or wrong server.
            with socket.socket() as candidate:
                candidate.bind(('127.0.0.1', 0))
                port = candidate.getsockname()[1]
            proxy = subprocess.Popen(['iproxy', '-u', udid, '-l' if route == 'usb' else '-n',
                '-s', '127.0.0.1', f'{port}:{config["port"]}'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 10
            while True:
                if proxy.poll() is not None:
                    raise AutomationError('paired_device_forwarder_exited')
                try:
                    stream = socket.create_connection(('127.0.0.1', port), timeout=1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise AutomationError('paired_device_forwarder_unavailable') from None
                    time.sleep(0.1)
            client = CommandTransport(stream, config['token'], expected_pid)
            client.snapshot()  # Authenticate/read-only; no launch/input mutation.
            device.command_transport = client
            yield client
        finally:
            if client is not None:
                client.close()
            # Retain the closed sentinel until explicit scope exit. Failures during
            # the context must never silently resend a mutation through XCTest.
            if getattr(device, 'command_transport', None) is client:
                device.command_transport = None
            if proxy is not None:
                proxy.terminate()
                try:
                    proxy.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proxy.kill(); proxy.wait(timeout=3)
