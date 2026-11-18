# 接口

`POST /api/run`：{"text":"CSV内容"}。同规则版本与输入摘要只产生一条批次；可选 `"resume":true` 从同一输入的已确认租约断点续算。

`POST /api/resume`：{"text":"CSV内容"}。从已确认租约续算；无断点返回404 NO_CHECKPOINT。

`GET/POST /api/1` 至 `/api/7`：独立样例或自定义文件计算。各模块返回 report、quarantine、balance。

`POST /api/review`：id、整数revision、decision取通过或退回。旧版本409；阻断项不能通过。阻断只针对真实超用/采购冲突，未领取撤回不阻断。

`GET /api/export/{id}`：唯一证据CSV。`GET /health`：存活检查。

## 证据CSV

除 manifest、result、quarantine 外，另含：

- `claim`：已领取依据（租约号、领取时刻、来源行、版本、裁决结果）；
- `correction`：误发补正依据（补正时刻、来源行、版本、结果）；
- `withdrawn_unclaimed`：未领取的已撤回租约（占席起止、原到期、补正行）；
- `attribution`：每个超用段的 available、user_excess、misissue_excess 与责任分配。

manifest 同时给出可用席位与使用人/误发补正席位小时汇总。

## 错误

结构/数值422，版本冲突409，不存在404，文件过大413，续算时无断点404，裁决中断409（携带已确认条数与断点租约号）。逐行异常进入quarantine。
