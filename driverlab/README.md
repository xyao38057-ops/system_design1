# DriverLab · 智能驾驶集成系统

面向“系统分析与设计”课程的可运行原型。包含二维路网、模拟车载传感器、路况事件、偏好加权路径推荐、用户行为规则分析、自动响应状态机和实验日志。

**当前网页使用自研的简化二维引擎，不依赖 SUMO 安装，也没有连接 SUMO。** 已克隆的 SUMO 保留在相邻的 `../references/sumo` 目录；本项目提供同一路网的 SUMO XML 导出脚本，供下一阶段接入使用。

## 1. 立即运行

环境：Python 3.10 或更高版本；已在本机 Python 3.11.6 验证。使用现代 Edge / Chrome 浏览器。

在 PowerShell 中执行：

```powershell
cd "F:\研一上\系统分析与设计\driverlab"
python server.py
```

看到 `DriverLab ready: http://127.0.0.1:8000` 后，在浏览器打开：

**http://127.0.0.1:8000**

运行网页不需要 `pip install`、`npm install`、Node.js、联网地图或任何 API Key。Python HTTP 服务、SQLite、前端 Canvas 都使用系统或浏览器现有能力。

- 保持这个终端运行；按 `Ctrl+C` 停止。
- 电脑关闭后，重新执行上述两行命令即可。历史事件保留在 SQLite 中，但正在运行的车辆不会从断电位置继续，启动后会创建新实验。
- 如果 8000 端口被占用：`python server.py --port 8001`，随后打开 `http://127.0.0.1:8001`。
- 如果找不到 `python`，先试 `py -3 server.py`。
- 不要双击 `static/index.html`；网页需要后端接口。
- 服务只监听本机 `127.0.0.1`。所有浏览器标签页共享同一个实验状态，暂不支持多用户独立实验。

## 2. 第一遍怎么体验

1. 在“驾驶总览”点击“正常导航”，选择 4× 加快演示；可随时暂停。
2. 进入“路径推荐”，比较距离、时间和舒适三个目标，点击应用偏好。
3. 回到总览，选择“中央街拥堵”或“道路封闭”，观察路线变化。
4. 选择“前车急停 · 侧方占用”，观察预警、制动和拒绝换道的理由。
5. 选择“前方障碍 · 可换道”，观察减速、2 秒换道和继续行驶。
6. 选择“测距传感器中断”，观察超时降级；点击前向测距旁的“恢复”。
7. 进入“用户行为”，切换模拟人工驾驶样本；进入“实验记录”，查看事件，点击右上角导出 CSV。

**选择预设场景会重置并自动运行；“重置”会重置当前场景并暂停。** 导航偏好在场景切换时保留。要比较同一场景，先统一偏好。

## 3. 已实现与实现边界

| 范围 | 已实现 | 当前边界 |
|---|---|---|
| 车载传感器网络 | 模拟定位、速度和前向距离；时间戳、断开、恢复、过期判断 | 没有真实 CAN/MQTT 设备、多传感器融合或视觉检测 |
| 路况监控 | 路段通行速度、拥堵/封闭/恢复事件、地图着色 | 速度由场景参数设定，没有从真实交通流估计 |
| 路径推荐 | Dijkstra、多偏好加权、动态重规划、无路可达处理 | 固定 A→D 小型有向路网；无交通灯等待预测 |
| 用户行为 | 120 秒固定种子合成数据、规则统计和评分 | 非真实用户数据；未训练分类模型；急加减速统计单位是采样点 |
| 自动响应 | 预警、制动、预设空间条件下换道、传感器超时停车 | 简化运动模型；侧车道占用由场景布尔量给出，非预测碰撞检查 |
| 实验记录 | SQLite 保存事件与运行摘要，CSV 导出 | 曲线仅保留当前运行最近 240 个采样点；无完整轨迹回放 |
| SUMO | XML 场景导出和可选 `netconvert` 调用脚本 | 未与网页实时联动；需另安装 SUMO 可执行程序 |

这些边界已在界面中注明。课程报告应描述实际实现，不能将二维演示写成真实自动驾驶验证或 SUMO 闭环控制。

## 4. 项目结构

```text
系统分析与设计/
├─ references/sumo/           # 已克隆的官方源码，保持原样
└─ driverlab/
   ├─ server.py              # 本地 HTTP API、线程调度、运行入口
   ├─ start.ps1              # 可选 PowerShell 启动入口
   ├─ app/
   │  ├─ network.py          # 路网、偏好权重、Dijkstra
   │  ├─ simulation.py       # 场景、车辆推进、传感器、响应状态机
   │  ├─ behavior.py         # 合成驾驶记录与规则分析
   │  └─ storage.py          # SQLite 事件与实验摘要
   ├─ static/               # HTML、CSS、JavaScript；无需构建
   ├─ tests/test_core.py     # 逻辑、持久化和 HTTP 集成测试
   ├─ tools/
   │  ├─ export_sumo.py      # 导出独立 SUMO 场景
   │  └─ browser_smoke.mjs   # 可选浏览器交互验证
   ├─ docs/                 # 分析设计、接口、分工、演示说明
   ├─ data/                 # 运行时 SQLite 数据，不建议提交 Git
   └─ artifacts/            # 生成场景、检查结果和截图，不建议提交 Git
```

## 5. 检查修改是否正确

在 `driverlab` 目录中运行：

```powershell
python -m unittest discover -s tests -v
```

测试只使用 Python 标准库，使用临时数据库，不修改你的正式实验日志。

修改 Python 后端后，需要停止并重新运行 `python server.py`；修改静态前端后刷新浏览器即可。

浏览器测试需要独立的 Chromium 调试实例和 Node 22+，不是运行项目的必需步骤。已保存的界面截图位于 `artifacts/`。

本机已通过 24 项后端/算法测试和 14 项浏览器检查，详见 [验证结果](docs/验证结果.md)。

## 6. 下一阶段：运行真正的 SUMO

目前已下载的是源码，不是安装好的仿真器。不建议在十几天的课程周期里从头编译 SUMO；可从官方 [Downloads](https://sumo.dlr.de/docs/Downloads.html) 获取 Windows 可执行发行包。

先导出 XML（无需安装 SUMO）：

```powershell
python tools/export_sumo.py
```

安装好 SUMO，并让 `netconvert`、`sumo-gui` 可以在终端找到后：

```powershell
python tools/export_sumo.py --build
sumo-gui -c artifacts/sumo/campus.sumocfg
```

若没有添加 PATH，则传入你电脑上实际的可执行文件路径，例如：

```powershell
python tools/export_sumo.py --build --netconvert "C:\Program Files (x86)\Eclipse\Sumo\bin\netconvert.exe"
```

安装位置可能不同，以你的实际路径为准。只导出 XML 时还没有 `campus.net.xml`；必须成功执行 `--build` 才能打开完整场景。

此独立场景包括同一拓扑、三条偏好路线、一辆主车和 24 辆背景车辆。它不会复现网页的急停/断传感器事件；后续需要通过 TraCI 适配层接入，详见 [分析设计](docs/分析设计.md)。

## 7. 八个人如何继续

先阅读 [八人协作与十二天计划](docs/开发分工.md)，按文件与接口拆分任务。演示前按照 [演示与验收](docs/演示与验收.md) 逐项检查。

技术接口见 [API 与数据约定](docs/API.md)。不要同时让多人直接修改 `simulation.py`；先由负责人拆分感知、策略与仿真适配模块，再分支开发。

如果需要给课程代码单独建 Git 仓库，可在 `driverlab` 中执行 `git init`。将 `driverlab` 作为团队项目提交即可，不必再把相邻的 SUMO 源码整个复制进来。

## 8. 参考来源

- [Eclipse SUMO 官方源码](https://github.com/eclipse-sumo/sumo)：本地参考仓库 `../references/sumo`，核查时提交 `6b4094c74`；原仓库未作修改。
- 本地官方教程：`../references/sumo/docs/web/docs/Tutorials/Hello_SUMO.md`。
- 本地 XML 格式说明：`../references/sumo/docs/web/docs/Networks/PlainXML.md`。

网页、规则模型、路网示例和课程文档为本次创建的原型代码。没有将 SUMO 源码复制改名为课程实现；SUMO 自身许可证保留在参考仓库中。
