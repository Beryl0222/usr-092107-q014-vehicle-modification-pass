# 汽车改装合规通行证

本仓库记录试点城市汽车改装合规通行证的领域对象、事件名称与基础校验方式，便于车主端、工坊、检测机构、监管、保险与路检系统交换一致的数据。

## 资料范围

- `contracts/domain.schema.json`：领域事件信封、聚合类型与事件名称目录。
- `data/sample.json`：一条用于本地联调的单条中文样例。
- `data/sample_stream.json`：一辆新能源车（露营取电电路 + 悬架 + 外观套件）从原厂登记到事故维修、部件转装、政策换版与复原更正的完整事件流。
- `src/validator.py`：事件信封校验（`validate_event`）与事件流语义校验（`validate_stream`）。
- `tests/`：信封、合法完整流与各类反例。

记录一经接收即只追加：标识、发生时间与版本不得原地改写，版本按聚合从 1 连续递增；更正只能发出版本号更高、以 `supersedes_event_id` 指向原记录的后继记录（`RECORD_CORRECTED`）。个人、机构及商业敏感信息仅向履行职责所需的调用方开放。

## 聚合与主线

以车辆识别码（VIN）为主线，覆盖以下聚合：

`vehicle_profile` 原厂配置 · `policy_regime` 政策版本 · `model_permission` 车型许可 · `modification_plan` 改装方案 · `part_record` 部件证书与绑定 · `technician_profile` 技师资质 · `oem_authorization` 车企三电/智驾授权 · `work_order` 施工工单 · `safety_gate` 安全门禁 · `inspection_decision` 检测结论 · `regulatory_approval` 监管审批 · `registration_change` 登记变更 · `insurance_decision` 保险批改 · `compliance_pass` 通行证 · `accident_repair` 事故维修 · `restoration_record` 复原记录。

## 关键语义（由 validate_stream 强制）

1. **政策按生效日期匹配，不溯及既往**：政策与车型许可必须携带 `effective_date`；方案在申报日钉选当时有效的最新版本（`POLICY_SNAPSHOT_PINNED`），此后新规则生效不会静默改变已批准方案的合法性。
2. **部件绑定与转装**：部件须先有认证记录才能绑定；同一部件转装其他车辆前必须先 `PART_UNBOUND` 解除原绑定，并经 `INSPECTION_SIGNED(scope=part_reinspection)` 重新检验后方可再次绑定。
3. **三电与驾驶辅助安全门禁**：域为 `traction_battery` 或 `driving_assistance` 的施工，必须先有车企授权（`OEM_AUTHORIZATION_GRANTED`）并通过安全门禁（`SAFETY_GATE_PASSED`），工坊不得申报。
4. **付款前预检**：`PRECONDITIONS_PUBLISHED` 向车主明示缺失的前置条件；受限域缺授权时必须如实列入 `missing`；存在缺失项不得开工。
5. **工坊只能申报自己的步骤**：`WORK_ATTESTED` 必须挂在本工坊已开的工单上，由具备资质的技师完成。
6. **独立结论**：检测、监管审批、保险批改必须由不同机构分别签署；通行证激活前检测、审批、登记变更（需要时）、保险结论缺一不可。
7. **数据最小化**：账本不承载商业报价、金额与个人行程/轨迹；普通美容项目（`cosmetic_appearance`）不得标记采集行驶数据。路检视图仅验证通行证当前有效状态，不读取报价与行程。

## 本地检查

```bash
python3 -m unittest discover -s tests
```
