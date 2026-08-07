import json

import tools.approval as approval
from tools.computer_use import tool as computer_use_tool
from tools.computer_use.backend import ActionResult


DENIED_COMMANDS = [
    "pmset sleepnow",
    "sudo pmset sleepnow",
    "command pmset sleepnow",
    "exec pmset sleepnow",
    "/bin/sh -c 'pmset sleepnow'",
    "zsh -c 'pmset sleepnow'",
    "sudo pmset sleep 10",
    "command pmset displaysleep 5",
    "exec pmset standby 1",
    "pmset -a standby 1",
    "/System/Library/CoreServices/Menu\\ Extras/User.menu/Contents/Resources/CGSession -suspend",
    "osascript -e 'tell application \"System Events\" to sleep'",
    "sudo osascript -e 'tell application \"System Events\" to log out'",
    "command osascript -e 'tell application \"System Events\" to restart'",
    "exec osascript -e 'tell application \"System Events\" to shut down'",
    "shutdown -h now",
    "sudo reboot",
    "command halt",
    "exec poweroff",
    "/bin/sh -c 'reboot'",
    "killall loginwindow",
    "pkill loginwindow",
    "sudo sysadminctl -screenLock on -password -",
    "sudo fdesetup enable",
    "sudo defaults write /Library/Preferences/com.apple.loginwindow autoLoginUser nobody",
    "sudo defaults delete /Library/Preferences/com.apple.loginwindow autoLoginUser",
    "sudo launchctl reboot system",
]

ALLOWED_HOUSEKEEPING_COMMANDS = [
    "osascript -e 'tell application \"Google Chrome\" to close front window'",
    "osascript -e 'tell application \"Docker\" to quit'",
    "osascript -e 'tell application \"Local\" to quit'",
    "pkill -f 'next dev -- --port 3217'",
    "ollama stop llama3.1:8b",
    "/usr/sbin/sysadminctl -screenLock status",
    "pmset -g custom",
    "/usr/bin/fdesetup status",
    "defaults read /Library/Preferences/com.apple.loginwindow autoLoginUser",
]


def test_headless_mac_terminal_hardline_denies_session_power_commands():
    for command in DENIED_COMMANDS:
        denied, description = approval.detect_hardline_command(command)
        assert denied, command
        assert "headless Mac power/session invariant" in description or description == "system shutdown/reboot"


def test_headless_mac_terminal_hardline_allows_housekeeping_and_posture_reads():
    for command in ALLOWED_HOUSEKEEPING_COMMANDS:
        denied, description = approval.detect_hardline_command(command)
        assert not denied, (command, description)


def test_headless_mac_computer_use_denies_gui_shortcuts_typed_set_value_and_system_ui_pointer():
    key_result = json.loads(computer_use_tool.handle_computer_use({"action": "key", "keys": "cmd+ctrl+q"}))
    assert key_result["code"] == "headless_mac_safety_denied"

    typed_result = json.loads(computer_use_tool.handle_computer_use({"action": "type", "text": "pmset sleepnow"}))
    assert typed_result["code"] == "headless_mac_safety_denied"

    menu_result = json.loads(computer_use_tool.handle_computer_use({"action": "set_value", "value": "Restart"}))
    assert menu_result["code"] == "headless_mac_safety_denied"

    semantic_system_result = json.loads(computer_use_tool.handle_computer_use({"action": "click", "app": "SystemUIServer", "element": 1}))
    assert semantic_system_result["code"] == "headless_mac_safety_denied"

    coordinate_system_result = json.loads(computer_use_tool.handle_computer_use({"action": "click", "app": "screen", "coordinate": [10, 10]}))
    assert coordinate_system_result["code"] == "headless_mac_safety_denied"


def test_headless_mac_computer_use_allows_housekeeping_text_and_shortcuts(monkeypatch):
    class DummyBackend:
        def key(self, keys, **kwargs):
            return ActionResult(ok=True, action="key", message="ok")

    monkeypatch.setattr(computer_use_tool, "_get_backend", lambda session_id="": DummyBackend())
    result = json.loads(computer_use_tool.handle_computer_use({"action": "key", "keys": "cmd+w"}))
    assert result.get("error") is None
