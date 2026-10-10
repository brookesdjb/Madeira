"""Reject ambiguous owners of runtime entry points before linking native experiments."""
import hashlib
from pathlib import Path
import re
import subprocess
from .device import AutomationError


def inspect_archive(path, required):
    path = Path(path)
    members = subprocess.check_output(["xcrun", "ar", "-t", str(path)], text=True).splitlines()
    symbols = subprocess.check_output(["xcrun", "nm", "-g", "-U", "-A", str(path)], text=True)
    counts = {name: 0 for name in required}
    for line in symbols.splitlines():
        match = re.search(r"(?:^|\s)[A-Z]\s+(_[A-Za-z0-9_]+)$", line)
        if match and match[1] in counts: counts[match[1]] += 1
    if len(members) != len(set(members)) or any(count != 1 for count in counts.values()):
        raise AutomationError("ambiguous_native_archive:" + path.name)
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "members": len(members), "entry_point_definitions": counts}


def inspect_native_inputs(root):
    specs = {"libwineserver.a": ["_main_loop", "_ios_srv_wake_sem"],
             "libntdll_unix.a": ["_wine_server_call", "_server_call_unlocked"]}
    return {name: inspect_archive(Path(root)/"app/Madeira"/name, symbols)
            for name, symbols in specs.items()}
