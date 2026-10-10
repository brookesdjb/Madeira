import platform
import subprocess
import pytest
from automation.controller.native_archives import inspect_archive
from automation.controller.device import AutomationError

pytestmark = pytest.mark.skipif(platform.system() != "Darwin", reason="Apple native archive tools")


def test_real_archive_rejects_two_owners_despite_distinct_member_names(tmp_path):
    objects = []
    for name in ("old", "new"):
        source = tmp_path/(name+".c"); obj = tmp_path/(name+".o")
        source.write_text("void main_loop(void) {}\nint ios_srv_wake_sem;\n")
        subprocess.run(["xcrun", "clang", "-c", str(source), "-o", str(obj)], check=True)
        objects.append(str(obj))
    archive = tmp_path/"runtime.a"
    subprocess.run(["xcrun", "ar", "rcs", str(archive), objects[0]], check=True)
    assert inspect_archive(archive, ["_main_loop", "_ios_srv_wake_sem"])["entry_point_definitions"]["_main_loop"] == 1
    subprocess.run(["xcrun", "ar", "r", str(archive), objects[1]], check=True)
    with pytest.raises(AutomationError, match="ambiguous_native_archive"):
        inspect_archive(archive, ["_main_loop", "_ios_srv_wake_sem"])
