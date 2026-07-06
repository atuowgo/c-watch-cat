"""手机放声服务: 在旧手机的 Termux 里运行, 把手机变成"吼声音箱".

这样吼声就从案发房间的手机里发出来, 而不是从别的房间的主机 ——
猫必须觉得"你就在现场", 条件反射才有效。

手机端安装 (每台旧手机做一次):
    1. 从 F-Droid 安装 Termux (Play 商店版已停更)
    2. 在 Termux 里:  pkg update && pkg install python mpv
    3. 把你的吼声录音传到手机 (termux-setup-storage 后放到 ~/alert.wav)
    4. 运行:  python phone_sound_server.py ~/alert.wav --port 8765
    5. Termux 里执行 ifconfig 记下手机 IP, 填进主机 config.yaml 的
       alert_url: "http://<手机IP>:8765/play"
    6. 建议: 路由器里给手机绑定固定 IP; Termux 设置里申请忽略电池优化

接口:
    GET /play?repeat=2   播放吼声 repeat 遍 (默认 1)
    GET /                健康检查, 返回状态文本
"""

import argparse
import shutil
import subprocess
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# 按顺序尝试: termux-media-player 需要 Termux:API 附加应用; mpv 最省事
_PLAYERS = [
    ("termux-media-player", ["play"], False),  # 非阻塞, 需靠 sleep 间隔
    ("mpv", ["--no-video", "--really-quiet"], True),
    ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"], True),
]

_play_lock = threading.Lock()


def find_player():
    for cmd, args, blocking in _PLAYERS:
        if shutil.which(cmd):
            return cmd, args, blocking
    return None, None, None


def play(sound, repeat):
    cmd, args, blocking = find_player()
    if cmd is None:
        print("!! 找不到播放器, 请在 Termux 里执行: pkg install mpv")
        return
    with _play_lock:  # 防止并发请求叠音
        for _ in range(repeat):
            subprocess.run([cmd, *args, str(sound)], check=False, timeout=30)
            if not blocking:
                time.sleep(4)  # termux-media-player 立即返回, 手动留出播放时间


class Handler(BaseHTTPRequestHandler):
    sound = None  # 由 main() 注入

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/play":
            qs = urllib.parse.parse_qs(parsed.query)
            try:
                repeat = max(1, min(5, int(qs.get("repeat", ["1"])[0])))
            except ValueError:
                repeat = 1
            threading.Thread(target=play, args=(self.sound, repeat),
                             daemon=True).start()
            self._respond(200, f"playing x{repeat}\n")
            print(f"[{time.strftime('%H:%M:%S')}] 收到放声请求 x{repeat}")
        elif parsed.path == "/":
            ok = self.sound.exists()
            self._respond(200 if ok else 500,
                          f"watch-cat sound node\nsound: {self.sound} "
                          f"({'ok' if ok else 'MISSING'})\n")
        else:
            self._respond(404, "not found\n")

    def _respond(self, code, text):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # 静默默认访问日志
        pass


def main():
    parser = argparse.ArgumentParser(description="watch-cat 手机放声服务")
    parser.add_argument("sound", help="吼声音频路径 (如 ~/alert.wav)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    sound = Path(args.sound).expanduser()
    if not sound.exists():
        raise SystemExit(f"音频文件不存在: {sound}")
    cmd, _, _ = find_player()
    if cmd is None:
        raise SystemExit("找不到播放器, 请先: pkg install mpv")

    Handler.sound = sound
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"放声服务已启动: http://0.0.0.0:{args.port}/play "
          f"(播放器: {cmd}, 音频: {sound})")
    print("请把 http://<本机IP>:{0}/play 填进主机 config.yaml 对应摄像头的 "
          "alert_url".format(args.port))
    server.serve_forever()


if __name__ == "__main__":
    main()
