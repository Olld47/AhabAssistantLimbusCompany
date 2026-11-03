"""临时诊断脚本：实测编队列表滚动的真实位移。

在游戏停在「队伍选择」页面时运行：

    .venv/bin/python tools/diagnose_team_scroll.py

脚本只做只读测量 + 可控的列表滚动，最后把列表复位到顶部，
不会点击任何队伍，也不会开始任务。

它会对比三种拖动方式，直接给出「哪种能真正滚动列表」：
  A. 当前配置的输入方式（mouse_swipe_for_team_scroll）
  B. 纯 PID 定向事件（后台 _drag）
  C. 借用真实光标（_drag_borrowing_cursor）
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from module.automation import auto  # noqa: E402
from module.automation.input_handlers.scroll_swipe import (  # noqa: E402
    build_windows_scroll_swipe_plan,
)
from module.config import cfg  # noqa: E402
from module.logger import log  # noqa: E402
from utils.path_manager import path_manager  # noqa: E402

ROW_UNITS = 72.5  # 1440 基准下的行高


def shot(deadline=20.0):
    """取一张截图；失败时最多等 deadline 秒，避免无限循环。"""
    end = time.time() + deadline
    while time.time() < end:
        img = auto.take_screenshot()
        if img is not None:
            return img
        time.sleep(0.2)
    raise RuntimeError(f"截图失败（{deadline}s 内未取到画面）")


def frame(bbox):
    return np.asarray(shot().convert("L").crop(bbox), dtype=np.float64)


def row_shift(before, after, max_shift=None):
    """归一化互相关求垂直位移（像素，正值表示内容整体下移）。"""
    h, w = before.shape
    if max_shift is None:
        # 一页最多滚 6 行，搜索范围必须覆盖，否则大位移会匹配到次优解。
        max_shift = h - 1
    a = before.mean(axis=1)
    b = after.mean(axis=1)
    a = a - a.mean()
    b = b - b.mean()
    best_off, best_score = 0, -np.inf
    for off in range(-max_shift, max_shift + 1):
        if off >= 0:
            x, y = a[off:], b[: h - off]
        else:
            x, y = a[: h + off], b[-off:]
        if x.size < h // 3:
            continue
        denom = np.linalg.norm(x) * np.linalg.norm(y)
        if denom == 0:
            continue
        score = float(np.dot(x, y) / denom)
        if score > best_score:
            best_off, best_score = off, score
    return best_off, best_score


def reset(my_position, scale):
    """把列表拉回顶部，便于下一次测量从同一起点开始。"""
    distance = max(0, cfg.set_win_size - my_position[1] - 60 * scale)
    for _ in range(8):
        auto.mouse_swipe_for_team_scroll(my_position[0], my_position[1], dy=distance, duration=0.3)
        time.sleep(0.4)


def measure(label, action, bbox, row_px):
    tag = label.split()[0]
    before_img = shot().convert("L").crop(bbox)
    save_frame(before_img, f"{tag}_before")
    before = np.asarray(before_img, dtype=np.float64)
    action()
    time.sleep(1.0)
    after_img = shot().convert("L").crop(bbox)
    save_frame(after_img, f"{tag}_after")
    after = np.asarray(after_img, dtype=np.float64)
    off, score = row_shift(before, after)
    rows = off / row_px
    log.info(f"[{label}] 位移 {off}px = {rows:.2f} 行 (相关度 {score:.3f})")
    return rows, score


OUT_DIR = Path(__file__).resolve().parents[1] / "logs" / "team_scroll_debug"


def check_permissions():
    """先自检权限，避免卡在截图里看不出原因。"""
    if sys.platform != "darwin":
        return True
    try:
        import Quartz
        from ApplicationServices import AXIsProcessTrusted
    except ImportError:
        log.warning("未安装 pyobjc，跳过权限自检")
        return True
    screen = bool(Quartz.CGPreflightScreenCaptureAccess())
    access = bool(AXIsProcessTrusted())
    log.info(f"权限自检: 屏幕录制={screen} 辅助功能={access}")
    if not screen:
        log.error(
            "没有屏幕录制权限，无法截图。请在「系统设置 → 隐私与安全性 → 屏幕录制」中\n"
            "勾选你当前使用的终端（Terminal/iTerm/VS Code），然后完全退出终端并重开。"
        )
        return False
    return True


def save_frame(image, name):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.png"
    image.save(path)
    log.info(f"截图已保存: {path}")
    return path


def main():
    if not check_permissions():
        return 2
    # 模板图路径必须先初始化，否则 find_element 找不到任何图片。
    path_manager.initialize_paths()
    auto.clear_img_cache()
    scale = cfg.set_win_size / 1440
    row_px = ROW_UNITS * scale
    log.info("=== 编队列表滚动诊断 ===")
    log.info(f"输入方式: {cfg.get_value('win_input_type')} / 行高 {row_px:.2f}px")

    shot()
    log.info("已取到游戏画面，开始定位队伍列表…")
    identify = auto.find_element("teams/identify_assets.png", take_screenshot=True)
    if not identify:
        log.error("没找到 teams/identify_assets.png —— 请确认游戏停在队伍选择页面")
        # 顺带把当前画面存下来，便于判断实际停在哪一页。
        save_frame(shot().convert("L"), "screen_not_team_page")
        return 1
    log.info(f"identify_assets 位置: {identify}")

    position = [identify[0] - 2150 * scale, identify[1] + 215 * scale]
    my_position = [position[0], 150 * scale + position[1]]
    first_position = [position[0], position[1] + 70 * scale]
    view_bbox = (0, int(position[1]), int(position[0] + 130 * scale), int(position[1] + 600 * scale))
    log.info(f"列表区域={view_bbox}")

    swipe_y = first_position[1] + 375 * scale
    page_dy = -362.5 * scale
    driver = auto.input_handler
    results = {}

    results["A 当前配置"] = measure(
        "A 当前配置",
        lambda: auto.mouse_swipe_for_team_scroll(first_position[0], swipe_y, dy=page_dy, duration=0.3),
        view_bbox,
        row_px,
    )
    reset(my_position, scale)

    if hasattr(driver, "_drag"):
        results["B 纯后台事件"] = measure(
            "B 纯后台事件",
            lambda: driver._drag(
                [(first_position[0], swipe_y), (first_position[0], swipe_y + page_dy)], 0.3, 0, True
            ),
            view_bbox,
            row_px,
        )
        reset(my_position, scale)

    if hasattr(driver, "_drag_borrowing_cursor"):
        plan, settle = build_windows_scroll_swipe_plan(first_position[0], swipe_y, 0, page_dy, 0.3)
        points = [p for p, _ in plan]
        steps = [max(0.01, s) for _, s in plan[1:]]
        results["C 借用光标"] = measure(
            "C 借用光标",
            lambda: driver._drag_borrowing_cursor(points, steps, settle or 0.3),
            view_bbox,
            row_px,
        )
        reset(my_position, scale)

    log.info("=== 结论 ===")
    for name, (rows, score) in results.items():
        verdict = "有效" if abs(rows) > 2 else "无效"
        log.info(f"  {name}: {rows:+.2f} 行 -> {verdict}")
    log.info("请把这几行发回来。期望一页 ≈ -5.00 行（向上拖 = 内容上移）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
