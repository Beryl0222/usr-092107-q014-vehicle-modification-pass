"""校验领域事件信封的基础字段与事件流的领域规则。

信封规则（validate_event）对应 contracts/domain.schema.json；
流规则（validate_stream）按接收顺序检查一条事件序列，
对应 README 中列出的领域约定 R1–R8。
"""

from datetime import datetime

REQUIRED = ("event_id", "event_type", "aggregate_type", "aggregate_id", "occurred_at", "version", "summary")

EVENT_TYPES = (
    "VEHICLE_REGISTERED",
    "POLICY_PUBLISHED",
    "PLAN_DECLARED",
    "PLAN_PRECHECKED",
    "PART_CERTIFIED",
    "PART_BOUND",
    "PART_UNBOUND",
    "OEM_AUTHORIZATION_RECORDED",
    "SAFETY_GATE_VERIFIED",
    "WORK_ORDER_ISSUED",
    "WORK_ATTESTED",
    "SOFTWARE_VERSION_RECORDED",
    "INSPECTION_SIGNED",
    "REGULATORY_APPROVED",
    "REGISTRATION_CHANGED",
    "INSURANCE_ENDORSED",
    "ACCIDENT_REPAIR_RECORDED",
    "RESTORATION_RECORDED",
    "PASS_ACTIVATED",
    "PASS_SUSPENDED",
    "PASS_REVOKED",
)

AGGREGATE_TYPES = (
    "vehicle_profile",
    "policy_permit",
    "modification_plan",
    "part",
    "oem_authorization",
    "work_order",
    "inspection_decision",
    "registration_change",
    "insurance_endorsement",
    "compliance_pass",
)

# 每种事件只能落在对应的聚合上。
EVENT_AGGREGATE = {
    "VEHICLE_REGISTERED": "vehicle_profile",
    "SOFTWARE_VERSION_RECORDED": "vehicle_profile",
    "ACCIDENT_REPAIR_RECORDED": "vehicle_profile",
    "RESTORATION_RECORDED": "vehicle_profile",
    "POLICY_PUBLISHED": "policy_permit",
    "PLAN_DECLARED": "modification_plan",
    "PLAN_PRECHECKED": "modification_plan",
    "REGULATORY_APPROVED": "modification_plan",
    "PART_CERTIFIED": "part",
    "PART_BOUND": "part",
    "PART_UNBOUND": "part",
    "OEM_AUTHORIZATION_RECORDED": "oem_authorization",
    "SAFETY_GATE_VERIFIED": "oem_authorization",
    "WORK_ORDER_ISSUED": "work_order",
    "WORK_ATTESTED": "work_order",
    "INSPECTION_SIGNED": "inspection_decision",
    "REGISTRATION_CHANGED": "registration_change",
    "INSURANCE_ENDORSED": "insurance_endorsement",
    "PASS_ACTIVATED": "compliance_pass",
    "PASS_SUSPENDED": "compliance_pass",
    "PASS_REVOKED": "compliance_pass",
}

# 涉及动力电池与驾驶辅助的改动类别，须先核验车企授权与安全门禁。
HIGH_RISK_CATEGORIES = ("power_battery", "driving_assistance")

# 普通美容项目不得收集的行驶数据字段。
DRIVING_DATA_KEYS = ("driving_data", "trip_history", "location_trace", "telemetry")

PASS_STATUS_BY_EVENT = {
    "PASS_ACTIVATED": "active",
    "PASS_SUSPENDED": "suspended",
    "PASS_REVOKED": "revoked",
}


def validate_event(record: dict) -> list[str]:
    errors = [f"缺少字段：{name}" for name in REQUIRED if name not in record]
    if "version" in record and (not isinstance(record["version"], int) or record["version"] < 1):
        errors.append("version 必须是正整数")
    event_type = record.get("event_type")
    if event_type is not None and event_type not in EVENT_TYPES:
        errors.append(f"未知事件类型：{event_type}")
    aggregate_type = record.get("aggregate_type")
    if aggregate_type is not None and aggregate_type not in AGGREGATE_TYPES:
        errors.append(f"未知聚合类型：{aggregate_type}")
    if event_type in EVENT_AGGREGATE and aggregate_type in AGGREGATE_TYPES:
        if EVENT_AGGREGATE[event_type] != aggregate_type:
            errors.append(f"事件 {event_type} 不能落在聚合 {aggregate_type} 上")
    occurred_at = record.get("occurred_at")
    if isinstance(occurred_at, str):
        parsed = _parse_time(occurred_at)
        if parsed is None:
            errors.append("occurred_at 必须是 ISO 8601 日期时间")
        elif parsed.tzinfo is None:
            errors.append("occurred_at 必须包含时区")
    return errors


# 以车辆识别码为主线的事件，payload 必须携带 vin。
VIN_SCOPED_EVENTS = {
    "VEHICLE_REGISTERED",
    "PLAN_DECLARED",
    "PART_BOUND",
    "PART_UNBOUND",
    "OEM_AUTHORIZATION_RECORDED",
    "SAFETY_GATE_VERIFIED",
    "WORK_ORDER_ISSUED",
    "SOFTWARE_VERSION_RECORDED",
    "INSPECTION_SIGNED",
    "REGISTRATION_CHANGED",
    "INSURANCE_ENDORSED",
    "ACCIDENT_REPAIR_RECORDED",
    "RESTORATION_RECORDED",
    "PASS_ACTIVATED",
    "PASS_SUSPENDED",
    "PASS_REVOKED",
}


def validate_stream(events: list[dict]) -> list[str]:
    """按接收顺序校验一条事件流，返回全部领域规则错误。"""
    errors: list[str] = []
    versions: dict[tuple[str, str], int] = {}
    policies: list[dict] = []
    bound_part_to_vin: dict[str, str] = {}
    authorizations: set[tuple[str, str]] = set()
    safety_gates: set[tuple[str, str]] = set()
    work_orders: dict[str, dict] = {}
    last_bound_at: dict[str, datetime] = {}
    inspections: dict[str, list[dict]] = {}
    endorsements: dict[str, list[dict]] = {}
    pass_status: dict[str, str] = {}

    for index, event in enumerate(events):
        label = event.get("event_id", f"第{index + 1}条")
        problems = validate_event(event)
        errors += [f"{label}：{problem}" for problem in problems]
        if problems:
            continue

        event_type = event["event_type"]
        payload = event.get("payload") or {}
        occurred_at = _parse_time(event["occurred_at"])
        vin = payload.get("vin")
        if event_type in VIN_SCOPED_EVENTS and not vin:
            errors.append(f"{label}：{event_type} 的 payload 缺少车辆识别码 vin")

        # R1 版本语义：同一聚合的版本只能递增，更正以新的后继记录表达。
        key = (event["aggregate_type"], event["aggregate_id"])
        previous = versions.get(key)
        if previous is not None and event["version"] <= previous:
            errors.append(f"{label}：聚合 {key[1]} 的版本从 {previous} 倒退到 {event['version']}")
        versions[key] = event["version"]

        if event_type == "POLICY_PUBLISHED":
            policies.append(payload)
        elif event_type == "PLAN_DECLARED":
            errors += _check_plan(label, payload, occurred_at, policies)
        elif event_type == "PART_BOUND":
            part_id = payload.get("part_id")
            current_vin = bound_part_to_vin.get(part_id)
            if current_vin is not None:
                errors.append(f"{label}：部件 {part_id} 仍绑定在 {current_vin}，转装前须先解除原绑定")
            if part_id:
                bound_part_to_vin[part_id] = vin
            if vin:
                last_bound_at[vin] = occurred_at
            errors += _check_high_risk_gate(label, vin, payload.get("categories") or [payload.get("category")], authorizations, safety_gates)
        elif event_type == "PART_UNBOUND":
            part_id = payload.get("part_id")
            if bound_part_to_vin.get(part_id) is None:
                errors.append(f"{label}：部件 {part_id} 未处于绑定状态，无法解除绑定")
            else:
                del bound_part_to_vin[part_id]
        elif event_type == "OEM_AUTHORIZATION_RECORDED":
            authorizations.add((vin, payload.get("scope")))
        elif event_type == "SAFETY_GATE_VERIFIED":
            safety_gates.add((vin, payload.get("scope")))
        elif event_type == "WORK_ORDER_ISSUED":
            work_orders[payload.get("work_order_id")] = payload
            errors += _check_high_risk_gate(label, vin, payload.get("categories") or [], authorizations, safety_gates)
        elif event_type == "WORK_ATTESTED":
            errors += _check_work_attestation(label, payload, work_orders)
        elif event_type == "INSPECTION_SIGNED":
            inspections.setdefault(vin, []).append({"at": occurred_at, "signer": payload.get("signer_org")})
        elif event_type == "INSURANCE_ENDORSED":
            endorsements.setdefault(vin, []).append({"at": occurred_at, "signer": payload.get("signer_org")})
        elif event_type in PASS_STATUS_BY_EVENT:
            errors += _check_pass_transition(label, event_type, vin, occurred_at, pass_status, last_bound_at, inspections, endorsements)

    return errors


def match_policy(policies: list[dict], when: datetime) -> dict | None:
    """按生效日期匹配政策：取 when 当日已生效的最新一版。

    已批准的方案始终匹配其申报时生效的版本，新政策不追溯既往。
    """
    effective = [p for p in policies if _effective_date(p) is not None and _effective_date(p) <= when.date()]
    if not effective:
        return None
    return max(effective, key=_effective_date)


def _check_plan(label: str, payload: dict, declared_at: datetime, policies: list[dict]) -> list[str]:
    errors = []
    policy = match_policy(policies, declared_at)
    if policy is None:
        return [f"{label}：申报之日没有已生效的政策与车型许可"]
    categories = {item.get("category") for item in payload.get("items", []) if item.get("category")}
    allowed = set(policy.get("allowed_categories") or categories)
    disallowed = set(policy.get("disallowed_categories") or ())
    for category in sorted(categories - allowed | categories & disallowed):
        errors.append(f"{label}：类别 {category} 不被申报时生效的政策 {policy.get('policy_id')} 允许")
    # R7 数据最小化：普通美容项目不得随方案收集行驶数据。
    if "cosmetic" in categories:
        for key in DRIVING_DATA_KEYS:
            if key in payload:
                errors.append(f"{label}：普通美容项目不应收集行驶数据字段 {key}")
    return errors


def _check_high_risk_gate(label: str, vin: str | None, categories, authorizations: set, safety_gates: set) -> list[str]:
    errors = []
    for category in categories:
        if category not in HIGH_RISK_CATEGORIES:
            continue
        if (vin, category) not in authorizations:
            errors.append(f"{label}：车辆 {vin} 缺少车企对 {category} 的授权")
        if (vin, category) not in safety_gates:
            errors.append(f"{label}：车辆 {vin} 未通过 {category} 的安全门禁核验")
    return errors


def _check_work_attestation(label: str, payload: dict, work_orders: dict[str, dict]) -> list[str]:
    order = work_orders.get(payload.get("work_order_id"))
    if order is None:
        return [f"{label}：申报的施工工单 {payload.get('work_order_id')} 不存在"]
    errors = []
    # R5 工坊只能申报自己工单内的步骤。
    if payload.get("workshop_id") != order.get("workshop_id"):
        errors.append(f"{label}：工坊 {payload.get('workshop_id')} 只能申报自己工单 {payload.get('work_order_id')} 的步骤")
    extra = set(payload.get("step_ids") or ()) - set(order.get("step_ids") or ())
    if extra:
        errors.append(f"{label}：申报了工单之外的步骤 {sorted(extra)}")
    return errors


def _check_pass_transition(
    label: str,
    event_type: str,
    vin: str | None,
    occurred_at: datetime,
    pass_status: dict[str, str],
    last_bound_at: dict[str, datetime],
    inspections: dict[str, list[dict]],
    endorsements: dict[str, list[dict]],
) -> list[str]:
    errors = []
    current = pass_status.get(vin, "none")
    if event_type == "PASS_ACTIVATED":
        if current == "active":
            errors.append(f"{label}：车辆 {vin} 的通行证已处于有效状态")
        # R2 转装后须重新检验：激活前须有不早于最近一次部件绑定的检验结论。
        bound_at = last_bound_at.get(vin)
        signed = [i for i in inspections.get(vin, []) if bound_at is None or i["at"] >= bound_at]
        if not signed:
            errors.append(f"{label}：车辆 {vin} 缺少部件绑定后的检验结论")
        if not endorsements.get(vin):
            errors.append(f"{label}：车辆 {vin} 缺少保险批改结论")
        # R6 检测与保险各自独立签署。
        if signed and endorsements.get(vin) and signed[-1]["signer"] == endorsements[vin][-1]["signer"]:
            errors.append(f"{label}：检测与保险结论须由不同机构独立签署")
    elif current != "active":
        errors.append(f"{label}：车辆 {vin} 当前无有效通行证，不能执行 {event_type}")
    if not errors:
        pass_status[vin] = PASS_STATUS_BY_EVENT[event_type]
    return errors


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _effective_date(policy: dict):
    value = policy.get("effective_from")
    if not isinstance(value, str):
        return None
    return _parse_time(value if "T" in value else f"{value}T00:00:00+00:00").date()
