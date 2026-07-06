"""配置加载: YAML 文件 + 默认值深合并, 并归一化为多摄像头结构.

支持两种写法:
1. 单摄像头 (一期): 顶层 camera + zones
2. 多摄像头组网 (二期): cameras 列表, 每个条目有自己的 name/source/zones/alert_url

load_config() 统一归一化成 cfg["cameras"] 列表, 主程序只处理列表。
"""

import copy

import yaml

DEFAULTS = {
    "camera": {
        "source": 0,       # 摄像头索引 / IP Webcam 地址 / RTSP / 视频文件
        "width": None,
        "height": None,
    },
    "cameras": [],         # 多摄像头写法, 非空时优先于 camera
    "detection": {
        "model": "yolov8n.pt",
        "confidence": 0.4,
        "imgsz": 640,
        "interval": 5,        # 每 N 帧跑一次 YOLO (帧间沿用上次的框)
        "miss_timeout": 1.5,  # 连续多少秒检测不到猫就认为猫离开了
    },
    "behavior": {
        "stationary_window": 2.5,
        "stationary_tolerance": 0.30,
        "scratch_motion_threshold": 4.0,
        "scratch_min_seconds": 1.5,
        "squat_ratio_drop": 0.75,
        "squat_min_seconds": 1.0,
        "trigger_on": "scratch",  # scratch | squat | both
    },
    "alert": {
        "sound": "sounds/alert.wav",
        "cooldown": 45,   # 全局冷却: 家里只有一只猫, 所有房间共享冷却时间
        "repeat": 2,
    },
    "zones": {
        "litter_box": [],  # 单摄像头写法下的区域配置
        "ignore": [],
    },
    "recording": {
        "enabled": True,
        "dir": "events",
        "pre_seconds": 8,
        "post_seconds": 5,
    },
}


def _deep_merge(base, override):
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _normalize_source(src):
    if isinstance(src, str) and src.isdigit():
        return int(src)
    return src


def _normalize(cfg):
    """把单摄像头/多摄像头两种写法统一成 cfg['cameras'] 列表."""
    cams = cfg.get("cameras") or []
    if not cams:
        cams = [{
            "name": "cam0",
            "source": cfg["camera"]["source"],
            "width": cfg["camera"].get("width"),
            "height": cfg["camera"].get("height"),
            "zones": cfg.get("zones", {}),
            "alert_url": None,
        }]
    normalized = []
    for i, cam in enumerate(cams):
        cam = dict(cam)
        cam.setdefault("name", f"cam{i}")
        cam.setdefault("width", None)
        cam.setdefault("height", None)
        cam.setdefault("alert_url", None)  # None = 在主机本地播放吼声
        cam["source"] = _normalize_source(cam.get("source", 0))
        zones = dict(cam.get("zones") or {})
        zones.setdefault("litter_box", [])
        zones.setdefault("ignore", [])
        cam["zones"] = zones
        normalized.append(cam)
    cfg["cameras"] = normalized
    return cfg


def load_config(path=None):
    user_cfg = {}
    if path:
        with open(path, encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
    return _normalize(_deep_merge(DEFAULTS, user_cfg))
