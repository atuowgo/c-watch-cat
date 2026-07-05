# watch-cat 🐱📹

监控猫在地板上拉屎的前兆行为, 自动播放主人的吼声, 把它"劝"回猫砂盆。

## 原理

很多猫在地板上拉屎前有固定的动作序列: **先原地用两只前爪扒拉地板, 然后摆出蹲姿**。
如果这时主人吼一声, 猫就会跑回猫砂盆。本项目把这个干预自动化:

```
摄像头 ──> YOLO 检测猫的位置 ──> 行为状态机 ──> 播放吼声录音 + 保存事件录像
                                    │
                                    ├─ 身体静止 (包围框中心不动)
                                    ├─ 前爪扒地 (框内运动量高)
                                    └─ 蹲姿 (框的高宽比骤降)
```

- 猫检测用 YOLO 预训练模型 (COCO 自带 cat 类别), **不需要自己训练**
- "扒地"通过 *身体不动但框内帧间差分很高* 来识别 —— 这正是原地刨地板的画面特征
- 猫砂盆区域可以画成白名单: 在盆里扒砂是好事, 不会报警
- 每次触发都会保存事件前 8 秒 + 后 5 秒的视频, 方便回看和调阈值

## 硬件

任何一种都行:

| 方案 | 说明 |
|------|------|
| 电脑 + USB 摄像头 | 最简单, 对准猫常"作案"的那片地板 |
| 旧手机 | 装个 IP 摄像头 App (如 IP Webcam), 把 RTSP/HTTP 地址填进 `config.yaml` |
| 树莓派 4/5 + 摄像头 | 可长期低功耗运行, 把 `imgsz` 降到 480、`interval` 调到 8 |

再加一个能出声的音箱 (电脑/树莓派自带喇叭也行, 声音要够大)。

## 安装

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 使用步骤

### 1. 录一段你的吼声 (关键!)

猫对**你的声音**有条件反射, 蜂鸣声效果差得多。用手机录一段你平时吼它的声音,
存成 `sounds/alert.wav` (手机录音可用 ffmpeg 转格式:
`ffmpeg -i 录音.m4a sounds/alert.wav`)。

赶时间的话可以先生成一个蜂鸣声兜底:

```bash
python tools/make_beep.py
```

### 2. 标定猫砂盆区域

```bash
python tools/calibrate_zone.py --config config.yaml
```

在画面上用鼠标点出猫砂盆的多边形区域 (按 `s` 保存)。猫在这个区域里
扒砂不会触发警报。如果食盆也在画面里, 按 `t` 切换到 ignore 类型把食盆
周围也框出来 —— 猫吃完饭常做"埋食物"的刨地动作, 容易误报。

### 3. 运行

```bash
# 先带窗口跑, 观察状态判断是否准确
python -m watchcat.main --config config.yaml --show

# 确认没问题后无界面长期运行
python -m watchcat.main --config config.yaml
```

窗口里会实时显示状态: `moving`(走动) → `stationary`(静止) →
`scratching`(扒地, 橙色) → `squatting`(蹲姿, 红色)。

### 4. 调阈值

每次触发都会在 `events/时间戳/` 下保存快照和视频。跑几天后回看:

- **误报多** (玩耍/舔毛被当成扒地): 调高 `scratch_motion_threshold`,
  或把 `trigger_on` 改成 `both` (要求先扒地后蹲下才报警)
- **漏报** (扒了地没触发): 调低 `scratch_motion_threshold` 或
  `scratch_min_seconds`
- **想更早介入**: `trigger_on: scratch` (默认, 扒地就报, 抢在蹲下之前)

## 测试

行为状态机是纯 Python 实现, 不装 opencv/YOLO 也能跑测试:

```bash
python -m pytest tests/ -v
```

## 一点养猫建议 (比代码更重要)

猫不用猫砂盆通常是有原因的, 这套系统治标, 下面这些治本:

1. **猫砂盆卫生**: 猫对气味极其敏感, 每天铲、每周换砂洗盆
2. **数量和位置**: 经验法则是 *猫的数量 + 1* 个盆, 放在安静、开阔、
   不被堵路的地方 (猫排泄时缺乏安全感就会换地方)
3. **砂的种类**: 有的猫嫌砂太粗/太香, 换一种细颗粒无味的试试
4. **及时就医**: 如果是突然开始乱拉, 可能是肠胃或泌尿问题, 先看兽医
5. **只在"现行"时制止**: 事后惩罚猫完全无法理解, 只会害怕你 ——
   这也正是本项目存在的意义: 永远在第一时间"现行"抓住它 😼

## 项目结构

```
watchcat/
├── main.py       主循环: 采集 -> 检测 -> 分析 -> 警报/录像
├── detector.py   YOLO 猫检测
├── behavior.py   行为状态机 (静止/扒地/蹲姿判定, 纯 Python)
├── alert.py      警报播放 (带冷却时间)
├── recorder.py   事件录像 (滚动缓冲, 保存触发前后片段)
├── geometry.py   多边形区域判定
└── config.py     配置加载
tools/
├── calibrate_zone.py  鼠标标定猫砂盆区域
└── make_beep.py       生成默认蜂鸣声
```
