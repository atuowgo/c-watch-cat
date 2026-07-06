"""配置归一化与警报调度测试 (不依赖 opencv/YOLO)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from watchcat.alert import AlertCoordinator  # noqa: E402
from watchcat.config import load_config  # noqa: E402


def write(tmp_path, text):
    p = tmp_path / "config.yaml"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_defaults_give_one_local_camera():
    cfg = load_config(None)
    assert len(cfg["cameras"]) == 1
    cam = cfg["cameras"][0]
    assert cam["name"] == "cam0"
    assert cam["source"] == 0
    assert cam["alert_url"] is None
    assert cam["zones"] == {"litter_box": [], "ignore": []}


def test_legacy_single_camera_style(tmp_path):
    """一期单摄像头写法: 顶层 camera + zones 仍然有效."""
    path = write(tmp_path, """
camera:
  source: "1"
zones:
  litter_box:
    - [[0, 0], [10, 0], [10, 10]]
""")
    cfg = load_config(path)
    cam = cfg["cameras"][0]
    assert cam["source"] == 1  # 数字字符串转成摄像头索引
    assert len(cam["zones"]["litter_box"]) == 1


def test_multi_camera_normalization(tmp_path):
    path = write(tmp_path, """
cameras:
  - name: living_room
    source: "http://192.168.1.101:8080/video"
    alert_url: "http://192.168.1.101:8765/play"
  - source: "http://192.168.1.102:8080/video"
""")
    cfg = load_config(path)
    cams = cfg["cameras"]
    assert len(cams) == 2
    assert cams[0]["name"] == "living_room"
    assert cams[0]["alert_url"] == "http://192.168.1.101:8765/play"
    assert cams[1]["name"] == "cam1"  # 没起名自动编号
    assert cams[1]["alert_url"] is None
    for cam in cams:
        assert cam["zones"] == {"litter_box": [], "ignore": []}


def test_behavior_config_matches_analyzer(tmp_path):
    from watchcat.behavior import BehaviorAnalyzer
    cfg = load_config(None)
    BehaviorAnalyzer(**cfg["behavior"])  # 参数名不匹配会 TypeError


def test_alert_global_cooldown():
    """全局冷却: 猫跨房间不应被连吼, 冷却过后可再触发."""
    c = AlertCoordinator(sound_path=None, cooldown=10, repeat=1)
    assert c.maybe_fire(alert_url=None, now=100.0)
    # 5 秒后另一个房间触发 -> 被全局冷却拦下
    assert not c.maybe_fire(alert_url=None, now=105.0)
    # 冷却过后再触发 -> 放行
    assert c.maybe_fire(alert_url=None, now=111.0)


def test_shadow_mode_records_without_sound():
    """影子模式: 触发照常返回 True (事件要记录), 但不派发放声."""
    c = AlertCoordinator(sound_path=None, cooldown=10, repeat=1,
                         enabled=False)
    fired_dispatch = []
    c._dispatch = lambda url: fired_dispatch.append(url)  # 出声即失败
    assert c.maybe_fire(alert_url=None, now=100.0)
    assert not c.maybe_fire(alert_url=None, now=105.0)  # 冷却照常生效
    assert fired_dispatch == []


def test_per_camera_behavior_override(tmp_path):
    """老手机噪点大, 单独调高该路的运动量阈值."""
    path = write(tmp_path, """
cameras:
  - name: living_room
    source: 0
    behavior:
      scratch_motion_threshold: 6.0
  - name: bedroom
    source: 1
""")
    cfg = load_config(path)
    merged = {**cfg["behavior"], **cfg["cameras"][0]["behavior"]}
    assert merged["scratch_motion_threshold"] == 6.0
    assert merged["scratch_min_seconds"] == cfg["behavior"]["scratch_min_seconds"]
    assert cfg["cameras"][1]["behavior"] == {}  # 没写覆盖 = 用全局值


def test_alert_enabled_default_true():
    cfg = load_config(None)
    assert cfg["alert"]["enabled"] is True
