import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.projections import missing_prerequisites, roadside_view
from src.validator import match_policy, validate_event, validate_stream

DATA_DIR = Path(__file__).parents[1] / "data"
TZ8 = timezone(timedelta(hours=8))
VIN_A = "LNBSCU3H0PD123456"


def load_stream() -> list[dict]:
    return json.loads((DATA_DIR / "sample_stream.json").read_text(encoding="utf-8"))


def without(stream: list[dict], event_id: str) -> list[dict]:
    return [event for event in stream if event["event_id"] != event_id]


def patched(stream: list[dict], event_id: str, **payload_changes) -> list[dict]:
    stream = copy.deepcopy(stream)
    for event in stream:
        if event["event_id"] == event_id:
            event["payload"].update(payload_changes)
    return stream


class StreamTest(unittest.TestCase):
    def setUp(self) -> None:
        self.stream = load_stream()

    def test_sample_stream_is_valid(self) -> None:
        self.assertEqual(validate_stream(self.stream), [])

    def test_versions_must_not_go_backwards(self) -> None:
        stream = copy.deepcopy(self.stream)
        stream[1]["version"] = 1
        errors = validate_stream(stream)
        self.assertTrue(any("版本" in error for error in errors), errors)

    def test_event_must_match_its_aggregate(self) -> None:
        event = {
            "event_id": "bad-001",
            "event_type": "PLAN_DECLARED",
            "aggregate_type": "vehicle_profile",
            "aggregate_id": "x",
            "occurred_at": "2026-08-10T14:00:00+08:00",
            "version": 1,
            "summary": "事件落在错误的聚合上",
        }
        self.assertTrue(any("不能落在聚合" in error for error in validate_event(event)))

    def test_rebind_requires_unbind_first(self) -> None:
        errors = validate_stream(without(self.stream, "stream-024"))
        self.assertTrue(any("解除原绑定" in error for error in errors), errors)

    def test_unbind_requires_existing_binding(self) -> None:
        extra = {
            "event_id": "bad-002",
            "event_type": "PART_UNBOUND",
            "aggregate_type": "part",
            "aggregate_id": "part-999",
            "occurred_at": "2026-10-03T09:00:00+08:00",
            "version": 1,
            "summary": "解除一个从未绑定的部件",
            "payload": {"part_id": "part-999", "vin": VIN_A},
        }
        errors = validate_stream(self.stream + [extra])
        self.assertTrue(any("未处于绑定状态" in error for error in errors), errors)

    def test_battery_work_requires_oem_authorization(self) -> None:
        errors = validate_stream(without(self.stream, "stream-009"))
        self.assertTrue(any("缺少车企对 power_battery 的授权" in error for error in errors), errors)

    def test_battery_work_requires_safety_gate(self) -> None:
        errors = validate_stream(without(self.stream, "stream-010"))
        self.assertTrue(any("安全门禁" in error for error in errors), errors)

    def test_workshop_attests_only_its_own_order(self) -> None:
        errors = validate_stream(patched(self.stream, "stream-015", workshop_id="ws-02"))
        self.assertTrue(any("只能申报自己工单" in error for error in errors), errors)

    def test_workshop_attests_only_steps_in_order(self) -> None:
        errors = validate_stream(
            patched(self.stream, "stream-015", step_ids=["s1-circuit", "s2-suspension", "s3-appearance", "s4-sunroof"])
        )
        self.assertTrue(any("工单之外的步骤" in error for error in errors), errors)

    def test_activation_requires_inspection_after_rebind(self) -> None:
        errors = validate_stream(without(self.stream, "stream-027"))
        self.assertTrue(any("缺少部件绑定后的检验结论" in error for error in errors), errors)

    def test_inspection_and_insurance_signed_independently(self) -> None:
        errors = validate_stream(patched(self.stream, "stream-020", signer_org="安测机动车检测所"))
        self.assertTrue(any("独立签署" in error for error in errors), errors)

    def test_cosmetic_plan_must_not_collect_driving_data(self) -> None:
        errors = validate_stream(patched(self.stream, "stream-031", trip_history=["2026-09-01 通勤轨迹"]))
        self.assertTrue(any("不应收集行驶数据" in error for error in errors), errors)

    def test_policy_matched_by_effective_date_and_grandfathered(self) -> None:
        policies = [e["payload"] for e in self.stream if e["event_type"] == "POLICY_PUBLISHED"]
        declared_at = datetime(2026, 8, 10, 14, 0, tzinfo=TZ8)
        policy = match_policy(policies, declared_at)
        self.assertEqual(policy["effective_from"], "2026-07-01")
        self.assertIn("appearance_kit", policy["allowed_categories"])
        # 新政策生效后再申报外观套件才被拒绝；plan-001 不因新规则变成违法。
        late_plan = {
            "event_id": "bad-003",
            "event_type": "PLAN_DECLARED",
            "aggregate_type": "modification_plan",
            "aggregate_id": "plan-003",
            "occurred_at": "2026-10-02T11:00:00+08:00",
            "version": 1,
            "summary": "新政策生效后申报外观套件",
            "payload": {"vin": VIN_A, "items": [{"name": "外观套件", "category": "appearance_kit"}]},
        }
        errors = validate_stream(self.stream + [late_plan])
        self.assertTrue(any("appearance_kit" in error for error in errors), errors)

    def test_roadside_view_shows_status_only(self) -> None:
        view = roadside_view(self.stream, VIN_A)
        self.assertEqual(view["pass_status"], "active")
        self.assertEqual(view["pass_id"], "pass-001")
        self.assertEqual(set(view), {"vin", "pass_status", "pass_id", "status_since", "last_inspection_at"})
        serialized = json.dumps(view, ensure_ascii=False)
        self.assertNotIn("26800", serialized)
        self.assertNotIn("quote", serialized)

    def test_roadside_view_reflects_suspension(self) -> None:
        suspended = {
            "event_id": "stream-032",
            "event_type": "PASS_SUSPENDED",
            "aggregate_type": "compliance_pass",
            "aggregate_id": "pass-001",
            "occurred_at": "2026-10-03T09:00:00+08:00",
            "version": 2,
            "summary": "通行证因复检暂缓有效",
            "payload": {"vin": VIN_A, "pass_id": "pass-001"},
        }
        self.assertEqual(validate_stream(self.stream + [suspended]), [])
        self.assertEqual(roadside_view(self.stream + [suspended], VIN_A)["pass_status"], "suspended")

    def test_missing_prerequisites_visible_before_payment(self) -> None:
        self.assertEqual(
            missing_prerequisites(self.stream, "plan-001"),
            ["oem_authorization:power_battery", "safety_gate:power_battery"],
        )


if __name__ == "__main__":
    unittest.main()
