"""Run the actual Foundation-only Swift parser/ledger, not a Python replica."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_native_command_validation_and_replay_ledger(tmp_path):
    if not shutil.which("swiftc"):
        pytest.skip("Swift compiler unavailable")
    main = tmp_path / "main.swift"
    main.write_text('''import Foundation
func parse(_ text: String) -> Bool { (try? AutomationCommand.parse(text)) != nil }
assert(parse(#"{"schema_version":2,"request_id":"r1","operation":"get_status"}"#))
assert(parse(#"{"schema_version":2,"request_id":"r2","operation":"launch_game","steam_app_id":400}"#))
for text in [
 #"{"schema_version":2,"request_id":"r","operation":"launch_game"}"#,
 #"{"schema_version":2,"request_id":"r","operation":"purchase_game"}"#,
 #"{"schema_version":2,"request_id":"r","operation":"get_status","path":"/tmp"}"#,
 #"{"schema_version":2,"request_id":"r","operation":"stop_game","steam_app_id":true}"#,
 #"{"schema_version":1,"request_id":"r","operation":"get_status"}"#,
 #"{"schema_version":2,"request_id":"r","operation":"launch_game","steam_app_id":400,"library_id":"11111111-1111-1111-1111-111111111111"}"#,
 String(repeating:"a",count:4097)] { assert(!parse(text)) }
var ledger = AutomationRequestLedger()
try ledger.accept("first")
do { try ledger.accept("first"); fatalError("replay accepted") } catch AutomationCommand.Failure.duplicate {}
for i in 0..<999 { try ledger.accept("id\\(i)") }
do { try ledger.accept("overflow"); fatalError("unbounded ledger") } catch AutomationCommand.Failure.limit {}
print("native_parser_and_ledger_passed")
''')
    source = Path(__file__).resolve().parents[2] / "app/Madeira/AutomationCommand.swift"
    executable = tmp_path / "command-test"
    subprocess.run(["swiftc", "-D", "DEBUG", "-D", "MADEIRA_AUTOMATION", str(source), str(main), "-o", str(executable)], check=True, capture_output=True, timeout=60)
    result = subprocess.run([str(executable)], check=True, capture_output=True, text=True, timeout=10)
    assert "native_parser_and_ledger_passed" in result.stdout
