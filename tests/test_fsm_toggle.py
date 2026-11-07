"""Unit tests cho SAFETY_FSM_ENABLED (Global Tool Mode) tại Edge."""
import os
import unittest
from unittest import mock

from feature.command.interlock import (
    InterlockViolation,
    check_room_command,
    is_edge_fsm_enabled,
)

ENV = "SAFETY_FSM_ENABLED"


class EdgeFsmToggleTests(unittest.TestCase):
    def test_global_tool_mode_when_fsm_disabled(self):
        with mock.patch.dict(os.environ, {ENV: "false"}):
            self.assertFalse(is_edge_fsm_enabled())
            # Mọi lệnh bị cấm ở M3 đều chạy global khi SAFETY_FSM_ENABLED=false:
            check_room_command("EXAM", "door", "unlocked", "ai_agent")
            check_room_command("LOCK", "door", "unlocked", "admin_hitl")
            check_room_command("EMERGENCY", "door", "locked", "ai_agent")
            check_room_command("EXAM", "buzzer", "on", "ai_agent")
            check_room_command("LOCK", "fan", "on", "ai_agent")
            check_room_command("LECTURE", "mode", "emergency", "ai_agent")

    def test_fsm_enforced_when_enabled(self):
        with mock.patch.dict(os.environ, {ENV: "true"}):
            self.assertTrue(is_edge_fsm_enabled())
            with self.assertRaises(InterlockViolation):
                check_room_command("EXAM", "door", "unlocked", "ai_agent")
            with self.assertRaises(InterlockViolation):
                check_room_command("EMERGENCY", "door", "locked", "ai_agent")
            with self.assertRaises(InterlockViolation):
                check_room_command("LECTURE", "mode", "emergency", "ai_agent")


if __name__ == "__main__":
    unittest.main()

