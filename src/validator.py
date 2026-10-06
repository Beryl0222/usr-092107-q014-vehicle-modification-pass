"""校验领域事件信封与事件流语义。

记录一经接收即只追加（append-only）：标识、发生时间与版本不得原地改写，
更正只能发出版本号更高的后继记录（RECORD_CORRECTED）。
"""

from datetime import date, datetime

REQUIRED = ("event_id", "event_type", "aggregate_type", "aggregate_id", "occurred_at", "version", "summary")

# 事件类型与所属聚合的对应关系；RECORD_CORRECTED 可发生在任意聚合上。
EVENT_AGGREGATES = {
    "FACTORY_CONFIG_RECORDED": {"vehicle_profile"},
    "POLICY_REGIME_ENACTED": {"policy_regime"},
    "MODEL_PERMISSION_EFFECTIVE": {"model_permission"},
    "PLAN_DECLARED": {"modification_plan"},
    "POLICY_SNAPSHOT_PINNED": {"modification_plan"},
    "PRECONDITIONS_PUBLISHED": {"modification_plan"},
    "PART_CERTIFICATE_RECORDED": {"part_record"},
    "PART_BOUND": {"part_record"},
    "PART_UNBOUND": {"part_record"},
    "TECHNICIAN_QUALIFIED": {"technician_profile"},
    "OEM_AUTHORIZATION_GRANTED": {"oem_authorization"},
    "WORK_ORDER_OPENED": {"work_order"},
    "SAFETY_GATE_PASSED": {"safety_gate"},
    "WORK_ATTESTED": {"work_order"},
    "SOFTWARE_VERSION_RECORDED": {"work_order"},
    "INSPECTION_SIGNED": {"inspection_decision"},
    "REGULATORY_APPROVAL_GRANTED": {"regulatory_approval"},
    "REGISTRATION_CHANGED": {"registration_change"},
    "INSURANCE_ENDORSEMENT_SIGNED": {"insurance_decision"},
    "PASS_ACTIVATED": {"compliance_pass"},
    "PASS_REVOKED": {"compliance_pass"},
    "ACCIDENT_REPAIR_RECORDED": {"accident_repair"},
    "RESTORATION_RECORDED": {"restoration_record"},
}

# 政策与车型许可必须携带生效日期，按生效日期匹配。
EFFECTIVE_DATE_EVENTS = {"POLICY_REGIME_ENACTED", "MODEL_PERMISSION_EFFECTIVE"}

# 涉及动力电池与驾驶辅助的改动属于受限域，必须先取得车企授权并通过安全门禁。
RESTRICTED_DOMAINS = {"traction_battery", "driving_assistance"}

# 普通美容项目不应过度收集行驶数据；账本中也不存放商业报价与个人行程。
COSMETIC_DOMAINS = {"cosmetic_appearance"}
FORBIDDEN_PAYLOAD_KEYS = {"quote", "quotation", "price", "amount", "trip_history", "trajectory", "行程", "报价", "金额"}


def _as_date(value) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def validate_event(record: dict) -> list[str]:
    """校验单条记录的信封自洽性。"""
    errors = [f"缺少字段：{name}" for name in REQUIRED if name not in record]
    if errors:
        return errors

    event_type = record["event_type"]
    if event_type not in EVENT_AGGREGATES and event_type != "RECORD_CORRECTED":
        errors.append(f"未知事件类型：{event_type}")

    allowed = EVENT_AGGREGATES.get(event_type)
    if allowed is not None and record["aggregate_type"] not in allowed:
        errors.append(f"{event_type} 不属于聚合 {record['aggregate_type']}")

    if not isinstance(record["version"], int) or record["version"] < 1:
        errors.append("version 必须是正整数")

    if event_type in EFFECTIVE_DATE_EVENTS and _as_date(record.get("effective_date")) is None:
        errors.append(f"{event_type} 必须携带合法的 effective_date")

    if event_type == "RECORD_CORRECTED" and not record.get("supersedes_event_id"):
        errors.append("RECORD_CORRECTED 必须以 supersedes_event_id 指向被更正的原记录")

    return errors


def validate_stream(records: list[dict]) -> list[str]:
    """校验整条事件流：版本语义、政策快照、部件转装、安全门禁与独立签署。"""
    errors: list[str] = []

    seen_ids: set[str] = set()
    versions: dict[str, int] = {}
    by_id: dict[str, dict] = {}

    # 政策匹配与方案上下文
    regime_effective: dict[str, list[tuple[date, int]]] = {}
    permission_effective: dict[str, list[tuple[date, int]]] = {}
    plans: dict[str, dict] = {}

    # 部件绑定状态机：part_id -> 当前绑定的 vehicle_id
    part_bindings: dict[str, str | None] = {}
    # 部件解除绑定后是否已重新检验
    part_reinspected: dict[str, bool] = {}

    # 受限域门禁：plan_id:domain -> 是否已授权/过门
    authorized: dict[tuple[str, str], bool] = {}
    gated: dict[tuple[str, str], bool] = {}

    # 独立签署：plan_id -> {环节: 机构标识}
    signers: dict[str, dict[str, str]] = {}
    # 登记变更：plan_id -> True 表示行驶证登记信息已完成变更
    registered: dict[str, bool] = {}

    # 前置条件预检：plan_id -> 是否不存在缺失项
    preconditions_clear: dict[str, bool] = {}
    # 技师资质：technician_id -> True
    qualified_techs: dict[str, bool] = {}
    # 工单归属：work_order_id -> workshop_id（工坊只能申报自己工单内的步骤）
    work_order_workshops: dict[str, str] = {}

    for record in records:
        rid = record.get("event_id", f"位置{len(seen_ids)}")
        prefix = f"[{rid}]"
        errors.extend(f"{prefix} {e}" for e in validate_event(record))
        if rid in seen_ids:
            errors.append(f"{prefix} event_id 重复，记录不得覆盖")
        seen_ids.add(rid)
        by_id[rid] = record

        aggregate_id = record.get("aggregate_id")
        version = record.get("version")
        if aggregate_id and isinstance(version, int):
            expected = versions.get(aggregate_id, 0) + 1
            if version != expected:
                errors.append(f"{prefix} 聚合 {aggregate_id} 版本应为 {expected}，实际为 {version}（只追加、不得跳号或改写）")
            versions[aggregate_id] = version

        event_type = record.get("event_type")
        payload = record.get("payload") or {}
        effective = _as_date(record.get("effective_date"))

        leaked = FORBIDDEN_PAYLOAD_KEYS.intersection(payload)
        if leaked:
            errors.append(f"{prefix} payload 不得承载商业报价或个人行程数据（{sorted(leaked)}），遵循数据最小化")

        if event_type == "RECORD_CORRECTED":
            target = by_id.get(record.get("supersedes_event_id"))
            if target is None:
                errors.append(f"{prefix} 更正指向的原记录不存在或位于其后")
            elif target.get("aggregate_id") != aggregate_id:
                errors.append(f"{prefix} 更正记录必须与原记录属于同一聚合")
            elif isinstance(version, int) and isinstance(target.get("version"), int) and version <= target["version"]:
                errors.append(f"{prefix} 更正记录版本必须高于原记录")

        elif event_type == "POLICY_REGIME_ENACTED" and effective:
            regime_effective.setdefault(aggregate_id, []).append((effective, version))
        elif event_type == "MODEL_PERMISSION_EFFECTIVE" and effective:
            permission_effective.setdefault(aggregate_id, []).append((effective, version))

        elif event_type == "PLAN_DECLARED":
            declared_on = _as_date(record.get("occurred_at"))
            plans[aggregate_id] = {
                "declared_on": declared_on,
                "pinned": False,
                "registration_required": bool(payload.get("registration_required", False)),
            }

        elif event_type == "POLICY_SNAPSHOT_PINNED":
            plan = plans.get(payload.get("plan_id", aggregate_id))
            regime_id = payload.get("policy_regime_id")
            permission_id = payload.get("model_permission_id")
            if plan is None:
                errors.append(f"{prefix} 政策快照必须钉选在已申报的方案上")
            else:
                plan["pinned"] = True
                for table, wanted, label in (
                    (regime_effective, regime_id, "政策版本"),
                    (permission_effective, permission_id, "车型许可版本"),
                ):
                    if wanted is None:
                        continue
                    candidates = [(d, v) for d, v in table.get(wanted, []) if plan["declared_on"] is None or d <= plan["declared_on"]]
                    if not candidates:
                        errors.append(f"{prefix} 钉选的{label}在方案申报日尚未生效")
                    elif max(candidates, key=lambda x: (x[0], x[1]))[1] != payload.get(
                        "policy_version" if label == "政策版本" else "permission_version"
                    ):
                        errors.append(f"{prefix} 钉选的{label}不是申报日生效的最新版本（已批准方案按当时规则评判，禁止静默套用新规则）")

        elif event_type == "PART_CERTIFICATE_RECORDED":
            part_bindings.setdefault(aggregate_id, None)

        elif event_type == "PART_UNBOUND":
            part_id = payload.get("part_id", aggregate_id)
            if part_bindings.get(part_id) is None:
                errors.append(f"{prefix} 部件 {part_id} 未绑定，不能解除绑定")
            part_bindings[part_id] = None
            part_reinspected[part_id] = False

        elif event_type == "INSPECTION_SIGNED" and payload.get("scope") == "part_reinspection":
            part_reinspected[payload.get("part_id")] = True

        elif event_type == "PART_BOUND":
            part_id = payload.get("part_id", aggregate_id)
            vehicle_id = payload.get("vehicle_id")
            if part_id not in part_bindings:
                errors.append(f"{prefix} 部件 {part_id} 缺少认证记录，不能绑定")
            elif part_bindings.get(part_id) is not None:
                errors.append(f"{prefix} 部件 {part_id} 仍绑定在其他车辆上，须先解除原绑定")
            elif part_id in part_reinspected and not part_reinspected[part_id]:
                errors.append(f"{prefix} 部件 {part_id} 转装前已解绑但未重新检验")
            part_bindings[part_id] = vehicle_id
            part_reinspected.setdefault(part_id, True)

        elif event_type == "OEM_AUTHORIZATION_GRANTED":
            for domain in payload.get("domains", []):
                authorized[(payload.get("plan_id"), domain)] = True

        elif event_type == "SAFETY_GATE_PASSED":
            domain = payload.get("domain")
            if domain in RESTRICTED_DOMAINS and not authorized.get((payload.get("plan_id"), domain)):
                errors.append(f"{prefix} {domain} 安全门禁缺少有效的车企三电/驾驶辅助授权")
            gated[(payload.get("plan_id"), domain)] = True

        elif event_type == "PRECONDITIONS_PUBLISHED":
            plan_id = payload.get("plan_id", aggregate_id)
            if plan_id not in plans:
                errors.append(f"{prefix} 前置条件预检必须挂在已申报的方案上")
            missing = payload.get("missing", [])
            preconditions_clear[plan_id] = not missing
            # 受限域方案若预检时缺失授权，必须显式列入缺失项。
            domains = payload.get("domains", [])
            for domain in domains:
                if domain in RESTRICTED_DOMAINS and not authorized.get((plan_id, domain)) and "oem_authorization" not in missing:
                    errors.append(f"{prefix} 预检未如实标记 {domain} 缺少车企授权，车主付款施工前有权知晓")

        elif event_type == "TECHNICIAN_QUALIFIED":
            qualified_techs[payload.get("technician_id", aggregate_id)] = True

        elif event_type == "WORK_ORDER_OPENED":
            work_order_workshops[aggregate_id] = payload.get("workshop_id")

        elif event_type == "WORK_ATTESTED":
            work_order_id = payload.get("work_order_id")
            workshop_id = payload.get("workshop_id")
            if work_order_id not in work_order_workshops:
                errors.append(f"{prefix} 工坊只能申报已开工工单内的步骤")
            elif workshop_id != work_order_workshops.get(work_order_id):
                errors.append(f"{prefix} 工坊 {workshop_id} 不能申报属于其他工坊的工单 {work_order_id}")
            technician_id = payload.get("technician_id")
            if technician_id is not None and not qualified_techs.get(technician_id):
                errors.append(f"{prefix} 技师 {technician_id} 缺少与施工域匹配的有效资质")
            domain = payload.get("domain")
            key = (payload.get("plan_id"), domain)
            if domain in RESTRICTED_DOMAINS and not authorized.get(key):
                errors.append(f"{prefix} 涉及{domain}的施工缺少车企授权，工坊不得申报")
            if domain in RESTRICTED_DOMAINS and not gated.get(key):
                errors.append(f"{prefix} 涉及{domain}的施工未通过安全门禁")
            if domain in COSMETIC_DOMAINS and payload.get("collects_driving_data"):
                errors.append(f"{prefix} 普通美容项目不得过度收集行驶数据")
            plan_id = payload.get("plan_id")
            if plan_id in preconditions_clear and not preconditions_clear[plan_id]:
                errors.append(f"{prefix} 前置条件尚有缺失，不得开工申报")

        elif event_type == "REGISTRATION_CHANGED":
            registered[payload.get("plan_id")] = True

        elif event_type in {"INSPECTION_SIGNED", "REGULATORY_APPROVAL_GRANTED", "INSURANCE_ENDORSEMENT_SIGNED"}:
            plan_id = payload.get("plan_id")
            org = payload.get("signer_org_id")
            stage = {
                "INSPECTION_SIGNED": "inspection",
                "REGULATORY_APPROVAL_GRANTED": "regulatory",
                "INSURANCE_ENDORSEMENT_SIGNED": "insurance",
            }[event_type]
            if plan_id and org:
                taken = signers.setdefault(plan_id, {})
                for other_stage, other_org in taken.items():
                    if other_org == org:
                        errors.append(f"{prefix} 检测、监管审批与保险结论必须由不同机构独立签署（{stage} 与 {other_stage} 同为 {org}）")
                taken[stage] = org

        elif event_type == "PASS_ACTIVATED":
            plan_id = payload.get("plan_id")
            plan_signers = signers.get(plan_id, {})
            for stage in ("inspection", "regulatory", "insurance"):
                if stage not in plan_signers:
                    errors.append(f"{prefix} 通行证激活前缺少 {stage} 环节的独立结论")
            if plan_id in plans and not plans[plan_id]["pinned"]:
                errors.append(f"{prefix} 通行证激活前未钉选政策快照")
            plan = plans.get(plan_id)
            if plan and plan["registration_required"] and not registered.get(plan_id):
                errors.append(f"{prefix} 该方案须先完成登记变更才能激活通行证")

    return errors
