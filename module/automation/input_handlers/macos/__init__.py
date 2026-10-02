"""macOS 专属输入后端。

- ``foreground_input``：CrossOver 前台输入（占用真实鼠标键盘）。
- ``background_input``：CrossOver 后台输入（事件定向投递给游戏进程）。
- ``playcover_control``：PlayCover (MaaTools) 设备的截图/触摸（走 MaaTools TCP 协议）。
- ``macos_keyboard``：Enter/P/ESC 的后台按键注入（``CGEventPostToPid``）。

这些模块依赖 PyObjC / Quartz，只能在 macOS 上导入；Windows 请使用
``input_handlers.input`` 中的实现。
"""


def foreground_input():
    """按需导入，避免在非 macOS 平台触发 PyObjC 依赖。"""
    from .foreground_input import Input

    return Input


def background_input():
    """按需导入，避免在非 macOS 平台触发 PyObjC 依赖。"""
    from .background_input import BackgroundInput

    return BackgroundInput
