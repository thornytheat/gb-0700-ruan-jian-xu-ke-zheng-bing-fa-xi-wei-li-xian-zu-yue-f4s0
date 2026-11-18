# 深度登记 软件许可证并发席位与离线租约

- 规模：中型
- 核心规则：按租约有效区间扫线统计并发，同刻先结束后开始；离线到期前始终占席，重复心跳不重复占用
- 派生规则：使用资格（租约）、采购覆盖（capacity）、责任（使用人/误发补正）分开记录；已领取租约不因补正中途停用，未覆盖席位不推给使用人

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 会话接收 | 运行会话接收并核对证据 | `POST /api/1` | `app/modules/m1_sessions/rules.py` | `tests/test_sessions.py` |
| M2 产品映射 | 运行产品映射并核对证据 | `POST /api/2` | `app/modules/m2_products/rules.py` | `tests/test_products.py` |
| M3 租约裁决 | 运行租约裁决并核对证据 | `POST /api/3` | `app/modules/m3_leases/rules.py` | `tests/test_leases.py`、`tests/test_corrections.py` |
| M4 并发扫描 | 运行并发扫描并核对证据 | `POST /api/4` | `app/modules/m4_concurrency/rules.py` | `tests/test_concurrency.py` |
| M5 超用归属 | 运行超用归属并核对证据 | `POST /api/5` | `app/modules/m5_excess/rules.py`、`app/attribution.py` | `tests/test_excess.py`、`tests/test_corrections.py` |
| M6 采购对照 | 运行采购对照并核对证据 | `POST /api/6` | `app/modules/m6_purchase/rules.py` | `tests/test_purchase.py` |
| M7 补传审计 | 运行补传审计并核对证据 | `POST /api/7` | `app/modules/m7_audit/rules.py` | `tests/test_audit.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现会怎样 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-02 | BOM | 静默采信错误值 | 首列清理 | `app/modules/m1_sessions/rules.py` | `tests/test_sessions.py::test_sessions_bom` |
| TRAP-08 | 前导零 | 静默采信错误值 | 字符串保存 | `app/modules/m1_sessions/rules.py` | `tests/test_sessions.py::test_sessions_id` |
| TRAP-11 | 时区混合 | 静默采信错误值 | UTC归一 | `app/modules/m2_products/rules.py` | `tests/test_products.py::test_product_timezone` |
| TRAP-13 | 乱序补传 | 静默采信错误值 | 事件端点排序 | `app/modules/m4_concurrency/rules.py` | `tests/test_concurrency.py::test_sweep_sample_sorted` |
| TRAP-14 | 重复心跳 | 静默采信错误值 | 不重复占席 | `app/modules/m1_sessions/rules.py` | `tests/test_sessions.py::test_sessions_duplicate` |
| TRAP-19 | 采购版冲突 | 静默采信错误值 | 显式版本优先级 | `app/modules/m5_excess/rules.py` | `tests/test_excess.py::test_excess_capacity_version` |
| TRAP-23 | 同刻交接 | 静默采信错误值 | 先结束后开始 | `app/modules/m4_concurrency/rules.py` | `tests/test_concurrency.py::test_sweep_boundary` |
| TRAP-26 | 陈旧补传 | 静默采信错误值 | 递增版本 | `app/modules/m7_audit/rules.py` | `tests/test_audit.py::test_audit_stale` |
| TRAP-31 | 已领取租约被补正作废 | 断网设备中途停用 | 领取早于补正则继续到原到期 | `app/modules/m3_leases/rules.py` | `tests/test_corrections.py::test_claim_before_correction_keeps_lease_until_expiry` |
| TRAP-32 | 误发占席记成个人超用 | 发行错误推给使用人 | 未覆盖席位记误发补正责任 | `app/modules/m5_excess/rules.py` | `tests/test_corrections.py::test_misissue_excess_not_charged_to_user` |
| TRAP-33 | 补正重试重复计责 | 责任翻倍 | 同版本同内容只留首次依据 | `app/modules/m3_leases/rules.py` | `tests/test_corrections.py::test_same_correction_retry_under_other_kind_alias_adds_no_responsibility` |
| TRAP-34 | 切换失败覆盖上版 | 许可结果丢失 | 保留上一版结果 | `app/modules/m3_leases/rules.py` | `tests/test_corrections.py::test_same_version_conflicting_correction_keeps_previous_result` |
| TRAP-35 | 中断后从头重算 | 已确认租约丢失 | 断点续算、结果一致 | `app/store.py` | `tests/test_corrections.py::test_resume_from_confirmed_leases_matches_full_run` |

## 对账规则

输入记录=采信记录+隔离记录+空行；重复记录归隔离；算法输出另记业务单位，不冒充输入行数。金额/浓度/时长使用Decimal；证据含原始行号。

## 已知不覆盖

不支持超过2MB输入，不执行生产自动放行；异常值需人员复核。全部计算只读本地事件，不发起厂商联网查询或采购动作。
