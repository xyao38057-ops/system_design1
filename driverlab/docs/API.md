# API 与数据约定

## 运行和时钟

基础地址：`http://127.0.0.1:8000`。只面向单机课程演示。一个服务进程只有一个共享实验。

仿真步长为 0.1 秒。工作线程约每 0.1 实际秒执行 1、2 或 4 个步长，取决于倍速。线程调度与磁盘写入可能带来延迟，因此倍速是演示控制，不是实时系统保证。前端约每 250 ms 发起一次状态查询。

内部位置与距离单位为 m，内部速度为 m/s，加速度为 m/s²，仿真时间为 s。接口 `vehicle.speed` 和速度曲线统一转换为 km/h。路段 `limit` 仍是 m/s。

## GET 接口

| 接口 | 输出 |
|---|---|
| `/api/health` | `{ok, engine, error}`，正常 HTTP 200，引擎失败 HTTP 503 |
| `/api/state` | 当前实验快照，结构见下表 |
| `/api/runs` | 最近 50 次实验摘要，按插入次序倒序 |
| `/api/export` | 全部持久化决策事件 CSV，UTF-8 BOM，触发文件下载 |

### 快照字段

| 字段 | 含义 |
|---|---|
| `engine` | 固定 `builtin-2d`，明确不是 SUMO |
| `run_id` | 当前实验标识；重置会创建新标识 |
| `scenario / scenario_name` | 场景代码 / 中文名称 |
| `running / completed` | 是否推进 / 是否到达目标 |
| `time / multiplier` | 仿真秒 / 倍速 |
| `status / reason` | 决策状态 / 当前理由 |
| `profile` | `balanced`（距离优先）、`fast`、`comfort` |
| `nodes / edges` | 节点坐标、路段属性和事件状态 |
| `route` | 当前路径及剩余距离和通行时间；完全无路时可为 null |
| `route_available` | 是否仍有通向 D 的完整路线；保留物理位置用的残余路径不算可达 |
| `candidates` | 三种偏好下，从 A 到 D 重新计算的候选路线；不可达项为 null |
| `vehicle` | 坐标、方向（弧度）、车道、换道进度、车速、加速度、里程、间距和 TTC |
| `sensor` | 测距在线状态、数据是否过期、最后更新时间和观测年龄 |
| `obstacle / side_blocked` | 固定前方障碍 / 预设侧方占用，用于可重复场景 |
| `metrics` | 重规划次数、碰撞标记、观测到的最小间距、减速度峰值 |
| `history` | 最新 240 个速度及加速度采样点 |
| `events` | 当前实验最新 100 个事件，倒序 |
| `behavior` | 模拟人工驾驶样本的规则统计，非本次自动驾驶画像 |
| `engine_error` | 工作线程异常消息；正常为 null |

距离观测在数据过期时为 null；TTC 在无前车、无接近速度或数据过期时为 null。不返回 NaN 或 Infinity。

## POST /api/action

请求头：`Content-Type: application/json`。浏览器只接受同源写请求。成功返回完整的新快照，参数错误返回 HTTP 400 和 `{"error":"原因"}`。

| 操作 | 请求例子 | 语义 |
|---|---|---|
| 开始 | `{"action":"start"}` | 推进当前场景；已结束需先重置 |
| 暂停 | `{"action":"pause"}` | 停止推进，保持当前状态 |
| 重置 | `{"action":"reset","scenario":"normal","profile":"balanced"}` | 创建新实验并暂停；未传偏好则保留当前偏好 |
| 预设场景 | `{"action":"scenario","scenario":"brake"}` | 创建新实验并自动开始 |
| 偏好 | `{"action":"profile","profile":"comfort"}` | 保留位置，重新规划后续路线 |
| 路况 | `{"action":"road","edge":"BC","operation":"close"}` | 操作可选 `close / congestion / restore` |
| 传感器 | `{"action":"sensor","online":false}` | 断开或恢复测距；online 必须为布尔值 |
| 行为样本 | `{"action":"behavior","style":"active"}` | `steady / active / cautious` 三类固定种子样本 |
| 倍速 | `{"action":"speed","multiplier":4}` | 只支持 1、2、4 |

场景代码：`normal / congestion / closure / brake / avoid / sensor / no_route`。

### PowerShell 示例

服务启动后，在另一个终端执行：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health

Invoke-RestMethod -Uri http://127.0.0.1:8000/api/action -Method Post -ContentType 'application/json' -Body '{"action":"scenario","scenario":"brake"}'
```

## 数据持久化

数据库默认是 `data/driverlab.sqlite3`，由服务自动创建。可通过 `python server.py --db 其他路径` 指定独立实验数据库。

`runs`：id、created_at（UTC）、scenario、profile、elapsed、status、metrics（JSON）。

`events`：自增 id、run_id、sim_time、kind、title、detail。

每次操作后、事件发生后及约每秒保存一次摘要。事件的时间是仿真时间；数据库创建时间是 UTC 实际时间。重启后保留历史，但当前车辆状态不会恢复。当前版本没有保存完整传感器流和动作输入快照；报告不能声称已实现逐帧回放。
