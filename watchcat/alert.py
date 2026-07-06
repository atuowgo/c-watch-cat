"""警报调度: 全局冷却 + 按房间路由.

家里只有一只猫, 所以冷却时间是全局的 —— 猫从客厅走到卧室不应该被连吼两次。
每个摄像头节点可以配 alert_url (手机上 Termux 跑的放声服务), 触发时向对应
房间的手机发 HTTP 请求, 让吼声从案发现场发出来; 没配 alert_url 则在主机
本地播放 (一期单机模式)。
"""

import logging
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger("watchcat.alert")

# 主机本地播放时按顺序尝试的命令行播放器
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


class LocalPlayer:
    """在主机本地播放吼声."""

    def __init__(self, sound_path):
        self.sound_path = Path(sound_path) if sound_path else None
        self._cmd, self._args = _find_player()
        if self.sound_path and not self.sound_path.exists():
            log.warning(
                "警报音频不存在: %s (可运行 python tools/make_beep.py 生成蜂鸣声, "
                "但强烈建议换成你自己吼声的录音)", self.sound_path)

    def play(self, repeat=1):
        for _ in range(max(1, repeat)):
            if self._cmd and self.sound_path and self.sound_path.exists():
                try:
                    subprocess.run(
                        [self._cmd, *self._args, str(self.sound_path)],
                        check=False, timeout=15,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    continue
                except Exception as exc:  # noqa: BLE001
                    log.error("本地播放失败: %s", exc)
            sys.stdout.write("\a")  # 兜底: 终端铃声
            sys.stdout.flush()
            time.sleep(0.5)


class AlertCoordinator:
    """全局冷却 + 路由到对应房间的手机 (或主机本地) 播放."""

    def __init__(self, sound_path, cooldown=45.0, repeat=2,
                 http_timeout=5.0):
        self.cooldown = cooldown
        self.repeat = max(1, repeat)
        self.http_timeout = http_timeout
        self._local = LocalPlayer(sound_path)
        self._last_fired = None
        self._lock = threading.Lock()

    def maybe_fire(self, alert_url=None, now=None):
        """不在冷却期则触发警报, 返回是否真的触发了."""
        now = time.time() if now is None else now
        with self._lock:
            if (self._last_fired is not None
                    and now - self._last_fired < self.cooldown):
                return False
            self._last_fired = now
        threading.Thread(
            target=self._dispatch, args=(alert_url,), daemon=True).start()
        return True

    def _dispatch(self, alert_url):
        if alert_url:
            url = alert_url
            sep = "&" if urllib.parse.urlparse(url).query else "?"
            url = f"{url}{sep}repeat={self.repeat}"
            try:
                with urllib.request.urlopen(url, timeout=self.http_timeout) as r:
                    r.read()
                log.info("已通知手机放声: %s", alert_url)
                return
            except Exception as exc:  # noqa: BLE001
                log.error("手机放声服务不可达 (%s): %s, 改用主机本地播放",
                          alert_url, exc)
        self._local.play(self.repeat)
