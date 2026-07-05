"""警报播放: 触发时播放主人吼声的录音 (带冷却时间)."""

import logging
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("watchcat.alert")

# 按顺序尝试的命令行播放器: (命令, 附加参数)
_PLAYERS = [
    ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
    ("paplay", []),
    ("aplay", ["-q"]),
    ("afplay", []),  # macOS
]


def _find_player():
    for cmd, args in _PLAYERS:
        if shutil.which(cmd):
            return cmd, args
    return None, None


class Alerter:
    def __init__(self, sound_path, cooldown=45.0, repeat=2):
        self.sound_path = Path(sound_path) if sound_path else None
        self.cooldown = cooldown
        self.repeat = max(1, repeat)
        self._last_fired = None
        self._player_cmd, self._player_args = _find_player()

        if self.sound_path and not self.sound_path.exists():
            log.warning(
                "警报音频不存在: %s (可以先运行 python tools/make_beep.py 生成蜂鸣声, "
                "但强烈建议换成你自己吼声的录音)", self.sound_path)
        if self._player_cmd is None:
            log.warning("没有找到可用的音频播放器 (ffplay/aplay/paplay/afplay), "
                        "触发时只会响终端铃声")

    def maybe_fire(self, now=None):
        """如果不在冷却期就触发警报, 返回是否真的触发了."""
        now = time.time() if now is None else now
        if self._last_fired is not None and now - self._last_fired < self.cooldown:
            return False
        self._last_fired = now
        threading.Thread(target=self._play, daemon=True).start()
        return True

    def _play(self):
        for _ in range(self.repeat):
            if (self._player_cmd and self.sound_path
                    and self.sound_path.exists()):
                try:
                    subprocess.run(
                        [self._player_cmd, *self._player_args,
                         str(self.sound_path)],
                        check=False, timeout=15,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    continue
                except Exception as exc:  # noqa: BLE001
                    log.error("播放音频失败: %s", exc)
            # 兜底: 终端铃声
            sys.stdout.write("\a")
            sys.stdout.flush()
            time.sleep(0.5)
