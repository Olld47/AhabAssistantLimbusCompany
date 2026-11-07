"""Read-only bundled assets; user configuration and logs stay outside the app."""
import os
import sys
from pathlib import Path


def prepare_data_directory():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
    data = Path(os.environ.get('AALC_DATA_DIR', Path.home() / 'Library/Application Support/AALC Mac'))
    data.mkdir(parents=True, exist_ok=True)
    for name in ('assets', 'i18n'):
        link = data / name
        target = root / name
        if link.is_symlink():
            if link.resolve() != target.resolve():
                temporary = data / (name + '.new')
                temporary.unlink(missing_ok=True)
                temporary.symlink_to(target, target_is_directory=True)
                temporary.replace(link)
        elif not link.exists():
            link.symlink_to(target, target_is_directory=True)
        else:
            raise RuntimeError(f'资源路径不是应用管理的链接，请选择空的数据目录: {link}')
    os.chdir(data)
    return data


def apply_mac_configuration(cfg):
    """应用 macOS 上真正不适用、或必须固定的配置。

    这里只放「用户设了也没意义」的项。像 simulator 这类有实际支持路径的开关
    （PlayCover 走触摸输入，代码里有完整分支）必须保留用户设置，
    否则每次启动都会把用户的选择悄悄改回去。
    """
    for key, value in {
        'set_win_size': 1080, 'set_windows': False, 'set_reduce_miscontact': False,
        'memory_protection': False, 'check_update': False, 'autostart': False,
        'after_completion_actions': [], 'after_completion_power_action': 'none',
        'image_resource_sync': False,
    }.items():
        cfg.unsaved_set_value(key, value)

    # background_click 只在 CrossOver 桌面版（非模拟器）下才有意义：
    # 模拟器输入方式由 simulator_type 决定，这里不覆盖用户的选择。
    getter = getattr(cfg, 'get_value', None)
    simulator_enabled = bool(getter('simulator', False)) if callable(getter) else False
    if not simulator_enabled:
        cfg.unsaved_set_value('background_click', False)
