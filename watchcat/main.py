"""主程序: 摄像头采集 -> 猫检测 -> 行为分析 -> 警报 + 事件录像.

用法:
    python -m watchcat.main --config config.yaml           # 无界面运行
    python -m watchcat.main --config config.yaml --show    # 带可视化窗口
    python -m watchcat.main --source test.mp4 --show       # 用视频文件调试
"""

import argparse
import logging
import time

import cv2
import numpy as np

from .alert import Alerter
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


def motion_in_bbox(prev_gray, gray, bbox):
    """计算包围框内的帧间差分均值 (0-255), 作为'扒地'运动量."""
    if prev_gray is None or bbox is None:
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


def run(cfg, show=False):
    cam = cfg["camera"]
    source = cam["source"]
    cap = cv2.VideoCapture(source)
    if isinstance(source, int):
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam["width"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam["height"])
    if not cap.isOpened():
        raise SystemExit(f"无法打开视频源: {source}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0 or fps > 120:
        fps = 15.0

    det_cfg = cfg["detection"]
    detector = CatDetector(det_cfg["model"], det_cfg["confidence"],
                           det_cfg["imgsz"])
    analyzer = BehaviorAnalyzer(**cfg["behavior"])
    alerter = Alerter(cfg["alert"]["sound"], cfg["alert"]["cooldown"],
                      cfg["alert"]["repeat"])
    rec_cfg = cfg["recording"]
    recorder = EventRecorder(rec_cfg["dir"], fps, rec_cfg["pre_seconds"],
                             rec_cfg["post_seconds"], rec_cfg["enabled"])
    zones = cfg["zones"]

    prev_gray = None
    bbox = None
    last_seen = 0.0
    last_state = None
    frame_idx = 0
    log.info("开始监控 (视频源: %s, 触发模式: %s)",
             source, cfg["behavior"]["trigger_on"])

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                log.info("视频源结束")
                break
            now = time.time()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if frame_idx % det_cfg["interval"] == 0:
                found = detector.detect(frame)
                if found is not None:
                    bbox = found
                    last_seen = now
                elif now - last_seen > det_cfg["miss_timeout"]:
                    bbox = None
            frame_idx += 1

            motion = motion_in_bbox(prev_gray, gray, bbox)
            prev_gray = gray

            if bbox is not None and in_zone(bbox, zones.get("litter_box", [])):
                # 在猫砂盆里扒砂是好事, 直接跳过并复位状态机
                analyzer.reset()
                state, triggered = State.MOVING, False
            elif bbox is not None and in_zone(bbox, zones.get("ignore", [])):
                analyzer.reset()
                state, triggered = State.MOVING, False
            else:
                state, triggered = analyzer.update(now, bbox, motion)

            if state != last_state:
                log.info("状态: %s", state.value)
                last_state = state

            recorder.push(now, frame)
            if triggered and alerter.maybe_fire(now):
                event_dir = recorder.trigger(now, frame)
                log.warning("⚠️  检测到拉屎前兆! 已播放警告声, 事件保存在 %s",
                            event_dir)

            if show:
                draw_overlay(frame, bbox, state, motion, zones)
                cv2.imshow("watch-cat", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        recorder.close()
        cap.release()
        if show:
            cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="监控猫的拉屎前兆行为")
    parser.add_argument("--config", default="config.yaml",
                        help="配置文件路径 (默认 config.yaml)")
    parser.add_argument("--source", default=None,
                        help="覆盖配置中的视频源 (摄像头索引/RTSP/视频文件)")
    parser.add_argument("--show", action="store_true", help="显示可视化窗口")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s")

    import os
    cfg_path = args.config if os.path.exists(args.config) else None
    if cfg_path is None:
        log.warning("找不到配置文件 %s, 使用默认配置", args.config)
    cfg = load_config(cfg_path)
    if args.source is not None:
        src = args.source
        cfg["camera"]["source"] = int(src) if src.isdigit() else src
    run(cfg, show=args.show)


if __name__ == "__main__":
    main()
