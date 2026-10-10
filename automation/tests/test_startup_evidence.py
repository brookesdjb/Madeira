from automation.controller.startup_evidence import classify_failures


def test_physical_runner_failure_is_actionable_without_exporting_private_text():
    summary = {"testFailures": [{"failureText": "The test runner failed to initialize for UI testing. (Underlying Error: Timed out while enabling automation mode.) private-token=SECRET"}]}
    assert classify_failures(summary) == ["ui_automation_mode_timeout"]


def test_unknown_diagnostic_is_not_exported_or_guessed():
    summary = {"testFailures": [{"failureText": "user@example.com password=SECRET some unknown platform failure"}]}
    assert classify_failures(summary) == ["unclassified_xctest_failure"]
