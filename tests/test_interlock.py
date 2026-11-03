"""Unit tests cho Edge FSM Interlock (pure logic, không cần DB/MQTT).

Chạy:  cd edge && python -m unittest tests.test_interlock -v
"""
import unittest

from feature.command.interlock import (
    InterlockViolation,
    StaleApprovalError,
    check_expected_state,
    check_room_command,
)


class InvariantTests(unittest.TestCase):
    def test_no_unlock_in_exam_or_lock_for_any_source(self):
        for mode in ("EXAM", "LOCK"):
            for src in ("ai_agent", "admin_hitl", "dtwin", "api"):
                with self.assertRaises(InterlockViolation) as ctx:
                    check_room_command(mode, "door", "unlocked", src)
                self.assertEqual(ctx.exception.code, "INV_A_NO_UNLOCK")

    def test_no_lock_in_emergency_for_any_source(self):
        for src in ("ai_agent", "admin_hitl", "dtwin"):
            with self.assertRaises(InterlockViolation) as ctx:
                check_room_command("EMERGENCY", "door", "locked", src)
            self.assertEqual(ctx.exception.code, "INV_B_NO_LOCK_EXIT")

    def test_unlock_allowed_in_emergency(self):
        check_room_command("EMERGENCY", "door", "unlocked", "admin_hitl")


class PermissionMatrixTests(unittest.TestCase):
    def test_exam_blocks_buzzer_for_ai(self):
        with self.assertRaises(InterlockViolation) as ctx:
            check_room_command("EXAM", "buzzer", "on", "admin_hitl")
        self.assertEqual(ctx.exception.code, "MODE_PERMISSION_DENIED")

    def test_lock_blocks_fan_and_door_for_ai(self):
        for ctype, val in (("fan", "on"), ("door", "locked"), ("light", "on")):
            with self.assertRaises(InterlockViolation):
                check_room_command("LOCK", ctype, val, "admin_hitl")

    def test_exam_allows_fan_for_ai(self):
        check_room_command("EXAM", "fan", "on", "ai_agent")

    def test_matrix_not_applied_to_human_direct_sources(self):
        # Người vận hành trực tiếp (DTwin panel) không bị ma trận AI, chỉ bị bất biến A/B.
        check_room_command("LOCK", "buzzer", "on", "dtwin")
        check_room_command("EXAM", "buzzer", "on", "admin")

    def test_unknown_mode_fails_closed_for_ai(self):
        with self.assertRaises(InterlockViolation):
            check_room_command("???", "fan", "on", "ai_agent")

    def test_autopilot_cannot_change_mode_but_hitl_can(self):
        with self.assertRaises(InterlockViolation) as ctx:
            check_room_command("LECTURE", "mode", "exam", "ai_agent")
        self.assertEqual(ctx.exception.code, "AUTOPILOT_NO_MODE_CHANGE")
        check_room_command("LECTURE", "mode", "exam", "admin_hitl")

    def test_case_and_whitespace_insensitive(self):
        with self.assertRaises(InterlockViolation):
            check_room_command(" exam ", "DOOR", " Unlocked ", "ADMIN_HITL")


class StaleApprovalTests(unittest.TestCase):
    def test_same_state_passes(self):
        check_expected_state("LECTURE", "v1", "lecture", "v1")

    def test_mode_changed_is_stale(self):
        with self.assertRaises(StaleApprovalError) as ctx:
            check_expected_state("EMERGENCY", "v2", "LECTURE", None)
        self.assertEqual(ctx.exception.expected, "LECTURE")
        self.assertEqual(ctx.exception.actual, "EMERGENCY")

    def test_a_to_b_to_a_detected_by_version(self):
        # Mode trở lại LECTURE nhưng đã qua một chu kỳ trạng thái khác => version khác.
        with self.assertRaises(StaleApprovalError):
            check_expected_state("LECTURE", "v3", "LECTURE", "v1")

    def test_no_expectation_means_no_check(self):
        check_expected_state("EMERGENCY", "v9", None, None)


if __name__ == "__main__":
    unittest.main()
