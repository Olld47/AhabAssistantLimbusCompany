# mac.14 平台实现

本分支面向原生 macOS 界面和 CrossOver Steam 游戏，沿用上游任务、OCR 与图像素材，不修改 CrossOver 或游戏二进制。

## 模块边界

- `module/macos/window.py`、`capture.py`、`geometry.py`：窗口查找、截图、Retina/标题栏坐标转换及输入前的窗口校验。
- `module/automation/input_handlers/background.py`：定向事件；`mouse_drag_map` 单独负责借用真实光标。普通后台点击、按键不移动系统指针。
- `module/macos/focus.py`、`control.py`：用户空闲、焦点恢复、暂停/停止和可取消等待。
- `tasks/mirror/search_road.py`：地图调整、节点连线识别、加权路线、缓存方向检查。
- `module/macos/recovery.py`：退出判定、日志归档、CrossOver/容器发现、Steam 重启、窗口/标题等待、频率限制。
- `tasks/base/script_task_scheme.py`：捕获镜牢的 `GameWindowLost`，重启后重新初始化输入和窗口，再进入镜牢流程。
- `tasks/base/retry_monitor.py`：恢复期间让监控线程等待，由主流程接管新窗口。

## CrossOver 滚动必须借用真实光标

**结论：CrossOver（Wine）下所有「滚动/拖动列表」的输入都不能用纯 PID 定向事件，必须借用系统真实光标。** 这是 CrossOver 端的实现问题，不是任务逻辑的问题——同一份选关代码在 PlayCover（触摸注入）上正常，在 CrossOver 上失效。

实测证据（纽本关卡列表，后台模式）：

| 方式 | 结果 |
| --- | --- |
| 纯 PID 定向拖动（`CGEventPostToPid`） | 滚动条位置完全不变，位移 **0** |
| 借用真实光标（`CGWarpMouseCursorPosition` + 定向事件） | 滚动条正常移动 |

原因是 Unity 的滚动/拖拽判定读的是 `GetCursorPos` 返回的**系统真实光标位置**，而不是事件里携带的坐标。纯定向事件能让**点击**生效（点按不依赖光标位置），但滚动不行。

因此后台模式（`BackgroundInput`）里这三类输入都走 `_drag_borrowing_cursor`：

- `mouse_swipe_for_team_scroll`：编队列表翻页；
- `mouse_drag_down`：通用列表滚动/翻页（纽本关卡列表用的就是它）；
- `mouse_drag_map`：镜牢地图相机拖动。

借用期间会等鼠标键盘空闲 1.5 秒，之后暂时接管光标、沿路径移动、松手后把光标放回原处。

## 恢复边界

`GameWindowLost → recover() → 游戏进程退出检查 → 保存日志 → Steam 启动 → 等窗口/标题 → init_game() → finish() → 返回主界面 → Mirror.run()`。

游戏仍运行、启动超时或退出频率超限均停止；不通过杀进程处理卡死。恢复期间 `in_progress` 协调主流程与监控线程。配置和日志在应用支持目录，签名包只存放代码与资源。

## 验证

运行 `python -m pytest -q`，测试目录包含后台输入清理、地图识别与路线、窗口几何、权限信息、意外退出恢复和队伍定位。测试不等同于完整镜牢实机验收；发布时分别记录自动测试结果与实机覆盖。
