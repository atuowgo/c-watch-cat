"""主程序: 多摄像头采集 -> 猫检测 -> 行为分析 -> 警报路由 + 事件录像.

一期 (单手机): config.yaml 里配一个摄像头即可。
二期 (多手机组网): cameras 列表配多个房间的手机, 主机统一检测,
触发时通知案发房间的手机播放吼声 (全局冷却, 避免猫跨房间被连吼)。

用法:
    python -m watchcat.main --config config.yaml           # 无界面运行
    python -m watchcat.main --config config.yaml --show    # 带可视化窗口
    python -m watchcat.main --source test.mp4 --show       # 用视频文件调试
"""

import argparse
import logging
import os
import threading
import time

import cv2
import numpy as np

from .alert import AlertCoordinator
from .behavior import BehaviorAnalyzer, State
from .config import load_config
from .detector import CatDetector
from .geometry import bbox_anchor, point_in_polygon
from .recorder import EventRecorder

log = logging.getLogger("watchcat")

STATE_COLORS = {
    State.NO_CAT: (128, 128, 128),
    State.MOVING: (0, 200, 0),
    State.STATIONARY: (0, 200, 200),
    State.SCRATCHING: (0, 120, 255),
    State.SQUATTING: (0, 0, 255),
}


class CameraStream(threading.Thread):
    """后台采集线程: 始终只保留最新一帧, 断流自动重连.

    手机 Wi-Fi 推流 (IP Webcam) 会偶尔掉线, 重连必须是常态而非异常。
    只保留最新帧也顺便解决了 RTSP 缓冲导致的画面延迟问题。
    """

    RECONNECT_DELAY = 3.0

    def __init__(self, name, source, width=None, height=None):
        super().__init__(daemon=True, name=f"stream-{name}")
        self.cam_name = name
        self.source = source
        self.width = width
        self.height = height
        self._lock = threading.Lock()
        self._frame = None
        self._seq = 0
        self._stopped = False
        self.ended = False  # 视频文件读完 (仅调试模式)
        self._is_file = (isinstance(source, str)
                         and not source.lower().startswith(
                             ("rtsp://", "http://", "https://")))
        self._file_fps = None

    def _open(self):
        cap = cv2.VideoCapture(self.source)
        if isinstance(self.source, int):
            if self.width:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            if self.height:
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if self._is_file:
            fps = cap.get(cv2.CAP_PROP_FPS)
            self._file_fps = fps if fps and 0 < fps <= 120 else 25.0
        return cap

    def run(self):
        cap = self._open()
        while not self._stopped:
            if not cap.isOpened():
                if self._is_file:
                    self.ended = True
                    return
                log.warning("[%s] 视频源断开, %.0f 秒后重连...",
                            self.cam_name, self.RECONNECT_DELAY)
                cap.release()
                time.sleep(self.RECONNECT_DELAY)
                cap = self._open()
                continue
            ok, frame = cap.read()
            if not ok:
                if self._is_file:
                    self.ended = True
                    cap.release()
                    return
                cap.release()  # 触发上面的重连分支
                continue
            with self._lock:
                self._frame = frame
                self._seq += 1
            if self._is_file:
                time.sleep(1.0 / self._file_fps)  # 文件调试时模拟实时速率
        cap.release()

    def latest(self):
        with self._lock:
            return self._seq, self._frame

    def stop(self):
        self._stopped = True


class CameraPipeline:
    """单个摄像头的完整处理状态 (检测框、行为状态机、录像器等)."""

    def __init__(self, cam_cfg, behavior_cfg, rec_cfg, fps=15.0):
        self.name = cam_cfg["name"]
        self.zones = cam_cfg["zones"]
        self.alert_url = cam_cfg["alert_url"]
        self.stream = CameraStream(self.name, cam_cfg["source"],
                                   cam_cfg["width"], cam_cfg["height"])
        self.analyzer = BehaviorAnalyzer(**behavior_cfg)
        self.recorder = EventRecorder(
            os.path.join(rec_cfg["dir"], self.name), fps,
            rec_cfg["pre_seconds"], rec_cfg["post_seconds"],
            rec_cfg["enabled"])
        self.prev_gray = None
        self.bbox = None
        self.last_seen = 0.0
        self.last_state = None
        self.last_seq = 0
        self.frame_idx = 0


def motion_in_bbox(prev_gray, gray, bbox):
    """计算包围框内的帧间差分均值 (0-255), 作为'扒地'运动量."""
    if prev_gray is None or bbox is None:
        return 0.0
    if prev_gray.shape != gray.shape:
        return 0.0
    h, w = gray.shape[:2]
    x1 = max(0, int(bbox[0]))
    y1 = max(0, int(bbox[1]))
    x2 = min(w, int(bbox[2]))
    y2 = min(h, int(bbox[3]))
    if x2 <= x1 or y2 <= y1:
        return 0.0
    diff = cv2.absdiff(prev_gray[y1:y2, x1:x2], gray[y1:y2, x1:x2])
    return float(np.mean(diff))


def in_zone(bbox, polygons):
    if bbox is None:
        return False
    anchor = bbox_anchor(bbox)
    return any(point_in_polygon(anchor, poly) for poly in polygons if poly)


def draw_overlay(frame, bbox, state, motion, zones):
    for poly in zones.get("litter_box", []):
        if poly:
            pts = np.array(poly, dtype=np.int32)
            cv2.polylines(frame, [pts], True, (255, 180, 0), 2)
            cv2.putText(frame, "litter box", tuple(pts[0]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 180, 0), 2)
    for poly in zones.get("ignore", []):
        if poly:
            pts = np.array(poly, dtype=np.int32)
            cv2.polylines(frame, [pts], True, (180, 180, 180), 2)

    color = STATE_COLORS.get(state, (255, 255, 255))
    if bbox is not None:
        x1, y1, x2, y2 = (int(v) for v in bbox)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.putText(frame, f"{state.value}  motion={motion:.1f}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    return frame


def process_frame(pipe, frame, now, detector, det_cfg, coordinator):
    """处理一个摄像头的一帧, 返回 (state, motion) 供可视化."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    if pipe.frame_idx % det_cfg["interval"] == 0:
        found = detector.detect(frame)
        if found is not None:
            pipe.bbox = found
            pipe.last_seen = now
        elif now - pipe.last_seen > det_cfg["miss_timeout"]:
            pipe.bbox = None
    pipe.frame_idx += 1

    motion = motion_in_bbox(pipe.prev_gray, gray, pipe.bbox)
    pipe.prev_gray = gray

    if pipe.bbox is not None and (
            in_zone(pipe.bbox, pipe.zones.get("litter_box", []))
            or in_zone(pipe.bbox, pipe.zones.get("ignore", []))):
        # 在猫砂盆里扒砂是好事; 食盆区埋食物动作则容易误报 —— 都跳过
        pipe.analyzer.reset()
        state, triggered = State.MOVING, False
    else:
        state, triggered = pipe.analyzer.update(now, pipe.bbox, motion)

    if state != pipe.last_state:
        log.info("[%s] 状态: %s", pipe.name, state.value)
        pipe.last_state = state

    pipe.recorder.push(now, frame)
    if triggered and coordinator.maybe_fire(pipe.alert_url, now):
        event_dir = pipe.recorder.trigger(now, frame)
        log.warning("⚠️  [%s] 检测到拉屎前兆! 已触发吼声, 事件保存在 %s",
                    pipe.name, event_dir)
    return state, motion


def run(cfg, show=False):
    det_cfg = cfg["detection"]
    detector = CatDetector(det_cfg["model"], det_cfg["confidence"],
                           det_cfg["imgsz"])
    coordinator = AlertCoordinator(
        cfg["alert"]["sound"], cfg["alert"]["cooldown"],
        cfg["alert"]["repeat"])

    pipes = [CameraPipeline(cam, cfg["behavior"], cfg["recording"])
             for cam in cfg["cameras"]]
    for p in pipes:
        p.stream.start()
        log.info("摄像头 [%s] 已启动: %s%s", p.name, p.stream.source,
                 f" -> 吼声路由 {p.alert_url}" if p.alert_url else " (主机放声)")
    log.info("开始监控 %d 路画面 (触发模式: %s)",
             len(pipes), cfg["behavior"]["trigger_on"])

    try:
        while True:
            got_frame = False
            for pipe in pipes:
                seq, frame = pipe.stream.latest()
                if frame is None or seq == pipe.last_seq:
                    continue
                pipe.last_seq = seq
                got_frame = True
                now = time.time()
                state, motion = process_frame(
                    pipe, frame, now, detector, det_cfg, coordinator)
                if show:
                    view = draw_overlay(frame.copy(), pipe.bbox, state,
                                        motion, pipe.zones)
                    cv2.imshow(f"watch-cat: {pipe.name}", view)

            if all(p.stream.ended for p in pipes):
                log.info("所有视频源结束")
                break
            if show:
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            if not got_frame:
                time.sleep(0.01)
    finally:
        for pipe in pipes:
            pipe.stream.stop()
            pipe.recorder.close()
        if show:
            cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="监控猫的拉屎前兆行为")
    parser.add_argument("--config", default="config.yaml",
                        help="配置文件路径 (默认 config.yaml)")
    parser.add_argument("--source", default=None,
                        help="覆盖为单摄像头模式 (摄像头索引/地址/视频文件), 调试用")
    parser.add_argument("--show", action="store_true", help="显示可视化窗口")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s")

    cfg_path = args.config if os.path.exists(args.config) else None
    if cfg_path is None:
        log.warning("找不到配置文件 %s, 使用默认配置", args.config)
    cfg = load_config(cfg_path)
    if args.source is not None:
        src = args.source
        cfg["cameras"] = [{
            "name": "debug",
            "source": int(src) if src.isdigit() else src,
            "width": None, "height": None,
            "zones": cfg.get("zones", {"litter_box": [], "ignore": []}),
            "alert_url": None,
        }]
    run(cfg, show=args.show)


if __name__ == "__main__":
    main()
