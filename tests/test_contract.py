import json
import unittest
from pathlib import Path

from src.validator import validate_event, validate_stream

DATA = Path(__file__).parents[1] / "data"


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def base(**overrides) -> dict:
    record = {
        "event_id": "e1",
        "event_type": "FACTORY_CONFIG_RECORDED",
        "aggregate_type": "vehicle_profile",
        "aggregate_id": "a1",
        "occurred_at": "2026-09-20T10:00:00+08:00",
        "version": 1,
        "summary": "x",
    }
    record.update(overrides)
    return record


class EnvelopeTest(unittest.TestCase):
    def test_sample_matches_envelope(self) -> None:
        self.assertEqual(validate_event(load("sample.json")), [])

    def test_effective_date_required_for_policy(self) -> None:
        record = base(event_type="POLICY_REGIME_ENACTED", aggregate_type="policy_regime", aggregate_id="p1")
        errors = validate_event(record)
        self.assertTrue(any("effective_date" in e for e in errors))

    def test_correction_requires_supersedes(self) -> None:
        record = base(event_type="RECORD_CORRECTED", aggregate_type="restoration_record")
        self.assertTrue(any("supersedes_event_id" in e for e in validate_event(record)))

    def test_event_must_match_aggregate(self) -> None:
        record = base(event_type="PART_BOUND", aggregate_type="vehicle_profile", aggregate_id="x1")
        self.assertTrue(any("不属于聚合" in e for e in validate_event(record)))


class SampleStreamTest(unittest.TestCase):
    def test_full_lifecycle_stream_is_valid(self) -> None:
        stream = load("sample_stream.json")
        self.assertEqual(validate_stream(stream["records"]), [])


class _StreamBuilder:
    """按样例裁剪出的最小合法方案流，供反例测试改写。"""

    def __init__(self) -> None:
        self._records = self._build()

    def records(self) -> list[dict]:
        return self._records

    @staticmethod
    def _build() -> list[dict]:
        return [
            base(event_id="r1", event_type="POLICY_REGIME_ENACTED", aggregate_type="policy_regime",
                 aggregate_id="p1", occurred_at="2026-03-01T00:00:00+08:00", effective_date="2026-03-01"),
            base(event_id="r2", event_type="MODEL_PERMISSION_EFFECTIVE", aggregate_type="model_permission",
                 aggregate_id="m1", occurred_at="2026-05-01T00:00:00+08:00", effective_date="2026-05-01"),
            base(event_id="r3", event_type="PLAN_DECLARED", aggregate_type="modification_plan",
                 aggregate_id="plan1", occurred_at="2026-09-01T00:00:00+08:00",
                 payload={"domains": ["traction_battery"], "registration_required": True}),
            base(event_id="r4", event_type="POLICY_SNAPSHOT_PINNED", aggregate_type="modification_plan",
                 aggregate_id="plan1", version=2, occurred_at="2026-09-01T00:05:00+08:00",
                 payload={"plan_id": "plan1", "policy_regime_id": "p1", "policy_version": 1,
                          "model_permission_id": "m1", "permission_version": 1}),
            base(event_id="r5", event_type="OEM_AUTHORIZATION_GRANTED", aggregate_type="oem_authorization",
                 aggregate_id="oa1", occurred_at="2026-09-02T00:00:00+08:00",
                 payload={"plan_id": "plan1", "domains": ["traction_battery"]}),
            base(event_id="r6", event_type="PRECONDITIONS_PUBLISHED", aggregate_type="modification_plan",
                 aggregate_id="plan1", version=3, occurred_at="2026-09-02T01:00:00+08:00",
                 payload={"plan_id": "plan1", "domains": ["traction_battery"], "missing": []}),
            base(event_id="r7", event_type="PART_CERTIFICATE_RECORDED", aggregate_type="part_record",
                 aggregate_id="part1", occurred_at="2026-09-03T00:00:00+08:00",
                 payload={"part_id": "part1"}),
            base(event_id="r8", event_type="PART_BOUND", aggregate_type="part_record",
                 aggregate_id="part1", version=2, occurred_at="2026-09-03T01:00:00+08:00",
                 payload={"part_id": "part1", "vehicle_id": "v1"}),
            base(event_id="r9", event_type="TECHNICIAN_QUALIFIED", aggregate_type="technician_profile",
                 aggregate_id="t1", occurred_at="2026-08-01T00:00:00+08:00",
                 payload={"technician_id": "t1"}),
            base(event_id="r10", event_type="WORK_ORDER_OPENED", aggregate_type="work_order",
                 aggregate_id="wo1", occurred_at="2026-09-04T00:00:00+08:00",
                 payload={"workshop_id": "w1", "plan_id": "plan1"}),
            base(event_id="r11", event_type="SAFETY_GATE_PASSED", aggregate_type="safety_gate",
                 aggregate_id="sg1", occurred_at="2026-09-04T01:00:00+08:00",
                 payload={"plan_id": "plan1", "domain": "traction_battery"}),
            base(event_id="r12", event_type="WORK_ATTESTED", aggregate_type="work_order",
                 aggregate_id="wo1", version=2, occurred_at="2026-09-04T02:00:00+08:00",
                 payload={"workshop_id": "w1", "work_order_id": "wo1", "technician_id": "t1",
                          "plan_id": "plan1", "domain": "traction_battery"}),
            base(event_id="r13", event_type="INSPECTION_SIGNED", aggregate_type="inspection_decision",
                 aggregate_id="id1", occurred_at="2026-09-05T00:00:00+08:00",
                 payload={"plan_id": "plan1", "signer_org_id": "org-inspect", "scope": "modification"}),
            base(event_id="r14", event_type="REGULATORY_APPROVAL_GRANTED", aggregate_type="regulatory_approval",
                 aggregate_id="ra1", occurred_at="2026-09-06T00:00:00+08:00",
                 payload={"plan_id": "plan1", "signer_org_id": "org-regulator"}),
            base(event_id="r15", event_type="REGISTRATION_CHANGED", aggregate_type="registration_change",
                 aggregate_id="rc1", occurred_at="2026-09-07T00:00:00+08:00",
                 payload={"plan_id": "plan1"}),
            base(event_id="r16", event_type="INSURANCE_ENDORSEMENT_SIGNED", aggregate_type="insurance_decision",
                 aggregate_id="in1", occurred_at="2026-09-08T00:00:00+08:00",
                 payload={"plan_id": "plan1", "signer_org_id": "org-insurer"}),
            base(event_id="r17", event_type="PASS_ACTIVATED", aggregate_type="compliance_pass",
                 aggregate_id="pass1", occurred_at="2026-09-09T00:00:00+08:00",
                 payload={"plan_id": "plan1"}),
        ]


class StreamRuleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = _StreamBuilder()

    def assertRejected(self, predicate: str) -> None:
        errors = validate_stream(self.builder.records())
        self.assertTrue(any(predicate in e for e in errors), f"预期命中“{predicate}”，实际：{errors}")

    def test_version_must_be_contiguous(self) -> None:
        for r in self.builder.records():
            if r["event_id"] == "r4":
                r["version"] = 3
        self.assertRejected("版本应为 2")

    def test_policy_not_yet_effective_may_not_be_pinned(self) -> None:
        for r in self.builder.records():
            if r["event_id"] == "r2":
                r["effective_date"] = "2026-10-01"
                r["occurred_at"] = "2026-10-01T00:00:00+08:00"
        self.assertRejected("尚未生效")

    def test_part_rebind_requires_unbind_and_reinspection(self) -> None:
        records = self.builder.records()
        # 未解除原绑定直接再次绑定同一部件
        records.append(base(event_id="r18", event_type="PART_BOUND", aggregate_type="part_record",
                            aggregate_id="part1", version=3, occurred_at="2026-09-10T00:00:00+08:00",
                            payload={"part_id": "part1", "vehicle_id": "v2"}))
        self.assertRejected("仍绑定在其他车辆")

        # 解绑后未重新检验不得绑定
        records[-1] = base(event_id="r19", event_type="PART_UNBOUND", aggregate_type="part_record",
                           aggregate_id="part1", version=3, occurred_at="2026-09-10T01:00:00+08:00",
                           payload={"part_id": "part1", "vehicle_id": "v1"})
        records.append(base(event_id="r20", event_type="PART_BOUND", aggregate_type="part_record",
                            aggregate_id="part1", version=4, occurred_at="2026-09-10T02:00:00+08:00",
                            payload={"part_id": "part1", "vehicle_id": "v2"}))
        errors = validate_stream(records)
        self.assertTrue(any("未重新检验" in e for e in errors), errors)

    def test_restricted_domain_requires_authorization_and_gate(self) -> None:
        records = [r for r in self.builder.records() if r["event_id"] not in {"r5", "r11"}]
        # 删除授权后预检仍宣称无缺失，预检必须报错；施工也必须报错
        errors = validate_stream(records)
        self.assertTrue(any("车企授权" in e for e in errors), errors)

    def test_workshop_may_only_attest_own_work_order(self) -> None:
        for r in self.builder.records():
            if r["event_id"] == "r12":
                r["payload"] = {**r["payload"], "workshop_id": "w2"}
        self.assertRejected("不能申报属于其他工坊")

    def test_unqualified_technician_rejected(self) -> None:
        for r in self.builder.records():
            if r["event_id"] == "r12":
                r["payload"] = {**r["payload"], "technician_id": "t-unknown"}
        self.assertRejected("缺少")

    def test_cosmetic_work_must_not_collect_driving_data(self) -> None:
        records = self.builder.records()
        for r in records:
            if r["event_id"] == "r3":
                r["payload"] = {"domains": ["cosmetic_appearance"], "registration_required": False}
            if r["event_id"] == "r4":
                r["payload"] = {**r["payload"]}
            if r["event_id"] == "r6":
                r["payload"] = {"plan_id": "plan1", "domains": ["cosmetic_appearance"], "missing": []}
        records = [r for r in records if r["event_id"] not in {"r5", "r8", "r11"}]
        for r in records:
            if r["event_id"] == "r12":
                r["payload"] = {"workshop_id": "w1", "work_order_id": "wo1", "technician_id": "t1",
                                "plan_id": "plan1", "domain": "cosmetic_appearance",
                                "collects_driving_data": True}
        errors = validate_stream(records)
        self.assertTrue(any("行驶数据" in e for e in errors), errors)

    def test_quote_and_trip_data_forbidden_in_payload(self) -> None:
        for r in self.builder.records():
            if r["event_id"] == "r10":
                r["payload"] = {**r["payload"], "quote": "8000元", "trip_history": []}
        self.assertRejected("数据最小化")

    def test_signers_must_be_independent_orgs(self) -> None:
        for r in self.builder.records():
            if r["event_id"] == "r16":
                r["payload"] = {**r["payload"], "signer_org_id": "org-inspect"}
        self.assertRejected("独立签署")

    def test_activation_requires_all_stages(self) -> None:
        records = [r for r in self.builder.records() if r["event_id"] != "r15"]
        errors = validate_stream(records)
        self.assertTrue(any("登记变更" in e for e in errors), errors)

    def test_correction_must_append_higher_version_same_aggregate(self) -> None:
        records = self.builder.records()
        records.append(base(event_id="r18", event_type="RECORD_CORRECTED", aggregate_type="restoration_record",
                            aggregate_id="other", version=1, occurred_at="2026-09-10T00:00:00+08:00",
                            supersedes_event_id="r17"))
        errors = validate_stream(records)
        self.assertTrue(any("同一聚合" in e for e in errors), errors)

    def test_work_cannot_start_with_unresolved_preconditions(self) -> None:
        for r in self.builder.records():
            if r["event_id"] == "r6":
                r["payload"] = {**r["payload"], "missing": ["part_certificate"]}
        self.assertRejected("前置条件尚有缺失")


if __name__ == "__main__":
    unittest.main()
