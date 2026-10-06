# 汽车改装合规通行证

本仓库记录该项目已确认的领域对象、事件名称和基础校验方式，便于不同系统交换一致的数据。

## 资料范围

- `contracts/domain.schema.json`：领域事件信封、聚合类型与事件名称。
- `data/sample.json`：一条用于本地联调的中文样例。
- `data/sample_stream.json`：一条覆盖完整生命周期的中文事件流样例（登记、申报、授权、施工、检验、审批、批改、激活，以及部件转装与复原）。
- `src/validator.py`：事件信封与事件流的最小校验代码。
- `src/projections.py`：面向不同角色的最小必要视图。
- `tests/`：验证样例与领域规则符合基础约定。

## 领域目录

以车辆识别码（vin）为主线，登记原厂配置、部件证书、施工工单、技师资质、软件版本、检测结果、监管审批、保险批改、事故维修与复原记录。

| 聚合 | 承载事件 |
| --- | --- |
| vehicle_profile | VEHICLE_REGISTERED、SOFTWARE_VERSION_RECORDED、ACCIDENT_REPAIR_RECORDED、RESTORATION_RECORDED |
| policy_permit | POLICY_PUBLISHED |
| modification_plan | PLAN_DECLARED、PLAN_PRECHECKED、REGULATORY_APPROVED |
| part | PART_CERTIFIED、PART_BOUND、PART_UNBOUND |
| oem_authorization | OEM_AUTHORIZATION_RECORDED、SAFETY_GATE_VERIFIED |
| work_order | WORK_ORDER_ISSUED、WORK_ATTESTED |
| inspection_decision | INSPECTION_SIGNED |
| registration_change | REGISTRATION_CHANGED |
| insurance_endorsement | INSURANCE_ENDORSED |
| compliance_pass | PASS_ACTIVATED、PASS_SUSPENDED、PASS_REVOKED |

## 领域规则

- R1 版本语义：记录一经接收，标识、发生时间与版本不得原地改写；同一聚合的版本只能递增，更正使用新的后继记录。
- R2 部件转装：同一部件转装其他车辆前，须先解除原绑定（PART_UNBOUND）并重新检验；通行证激活要求存在不早于最近一次部件绑定的检验结论。
- R3 高风险门禁：涉及动力电池（power_battery）与驾驶辅助（driving_assistance）的改动，绑定部件与开立工单前须核验车企授权与安全门禁。
- R4 生效日期匹配：政策与车型许可按生效日期匹配方案申报日；已批准的方案不因新规则被静默改成违法。
- R5 工坊范围：工坊只能申报自己开立工单内的施工步骤。
- R6 独立签署：检测与保险机构各自签署独立结论，不得由同一机构署名。
- R7 数据最小化：普通美容（cosmetic）项目不得收集行驶数据；个人、机构及商业敏感信息仅向履行职责所需的调用方开放。
- R8 前置条件可见：PLAN_PRECHECKED 记录付款施工前仍缺的前置条件，`missing_prerequisites` 视图供车主查询。

## 角色视图

`src/projections.py` 只从白名单事件与字段投影：

- `roadside_view`：路检人员验证当前有效状态（active / suspended / revoked / none），看不到商业报价与个人行程。
- `missing_prerequisites`：车主在付款施工前知道方案仍缺哪些前置条件。

## 本地检查

```bash
python3 -m unittest discover -s tests
```
