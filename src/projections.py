"""面向不同角色的最小必要视图。

视图只从白名单事件与字段投影，商业报价、个人行程等
与履职无关的信息不会进入视图。
"""

from src.validator import PASS_STATUS_BY_EVENT


def roadside_view(events: list[dict], vin: str) -> dict:
    """路检视图：仅当前有效状态与必要标识，看不到报价与行程。"""
    view = {"vin": vin, "pass_status": "none", "pass_id": None, "status_since": None, "last_inspection_at": None}
    for event in events:
        payload = event.get("payload") or {}
        if payload.get("vin") != vin:
            continue
        if event["event_type"] in PASS_STATUS_BY_EVENT:
            view["pass_status"] = PASS_STATUS_BY_EVENT[event["event_type"]]
            view["pass_id"] = payload.get("pass_id")
            view["status_since"] = event["occurred_at"]
        elif event["event_type"] == "INSPECTION_SIGNED":
            view["last_inspection_at"] = event["occurred_at"]
    return view


def missing_prerequisites(events: list[dict], plan_id: str) -> list[str]:
    """车主付款施工前可查询：方案最近一次前置条件核对仍缺哪些项。"""
    missing: list[str] = []
    for event in events:
        if event["event_type"] == "PLAN_PRECHECKED" and event["aggregate_id"] == plan_id:
            missing = list((event.get("payload") or {}).get("missing_prerequisites") or [])
    return missing
