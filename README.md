# watch-cat 🐱📹

监控猫在地板上拉屎的前兆行为, 自动播放主人的吼声, 把它"劝"回猫砂盆。

建设路线: **一期** 一台旧手机盯住案发高发区 → **二期** 多台旧手机多房间组网
(应对猫学精换地方作案) → **终极形态** 移动机器人跟踪 (见
[docs/product-design.md](docs/product-design.md))。

## 原理

很多猫在地板上拉屎前有固定的动作序列: **先原地用两只前爪扒拉地板, 然后摆出蹲姿**。
如果这时主人吼一声, 猫就会跑回猫砂盆。本项目把这个干预自动化:

```
旧手机(每房间一台)                    主机(家里任一台电脑)
┌────────────────────┐   Wi-Fi    ┌──────────────────────────┐
│ IP Webcam 推视频流  │ ─────────> │ YOLO 猫检测               │
│                    │            │  → 行为状态机 (扒地/蹲姿)  │
│ Termux 放声服务     │ <───────── │  → 全局警报调度            │
│  (播放你的吼声)     │  HTTP触发  │  → 事件录像 events/<房间>/ │
└────────────────────┘            └──────────────────────────┘
```

- 每台旧手机 = 摄像头 + 音箱二合一: 吼声从**案发现场的手机**发出来,
  猫才会觉得"你就在场"
- 猫检测用 YOLO 预训练模型 (COCO 自带 cat 类别), **不需要自己训练**
- "扒地"通过 *身体不动但框内帧间差分很高* 来识别
- 猫砂盆区域画成白名单: 在盆里扒砂是好事, 不报警
- 全局冷却 45 秒: 猫从客厅走到卧室, 不会被两台手机连着吼
- 每次触发保存事件前 8 秒 + 后 5 秒视频, 方便回看和调阈值

## 安装 (主机端)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 手机节点安装 (每台旧手机做一次, 约 15 分钟)

**A. 摄像头 (IP Webcam)**

1. 安装 [IP Webcam](https://play.google.com/store/apps/details?id=com.pas.webcam)
   (或酷安等应用市场)
2. 设置分辨率 720p、关闭音频, 点「开始服务」
3. 屏幕上会显示地址如 `http://192.168.1.101:8080`,
   视频流就是 `http://192.168.1.101:8080/video`

**B. 音箱 (Termux 放声服务)**

1. 从 [F-Droid](https://f-droid.org/packages/com.termux/) 安装 Termux
   (Play 商店版已停更)
2. Termux 里执行: `pkg update && pkg install python mpv`
3. 用手机录一段**你平时吼猫的声音**存为 `~/alert.wav`
   (这一步是灵魂 —— 猫对你的声音才有条件反射, 蜂鸣声效果差得多)
4. 把本仓库的 `tools/phone_sound_server.py` 传到手机, 运行:
   `python phone_sound_server.py ~/alert.wav --port 8765`
5. 浏览器访问 `http://<手机IP>:8765/play` 测试, 手机应播放吼声

**C. 稳定性设置 (重要)**

- 手机常插电源, 屏幕调最暗
- 路由器里给每台手机**绑定固定 IP** (DHCP 静态租约)
- 系统设置里对 IP Webcam 和 Termux **关闭电池优化**, Termux 开启唤醒锁
  (通知栏 Acquire wakelock)

## 使用步骤

### 1. 配置摄像头

编辑 `config.yaml`, 把手机 IP 填进去:

```yaml
cameras:
  - name: living_room
    source: "http://192.168.1.101:8080/video"
    alert_url: "http://192.168.1.101:8765/play"
```

二期加房间 = 加一个条目, 其他什么都不用改。

### 2. 标定猫砂盆区域

```bash
python tools/calibrate_zone.py --camera living_room
```

鼠标点出猫砂盆的多边形 (按 `s` 保存)。食盆如果在画面里, 按 `t` 切到
ignore 类型也框出来 —— 猫饭后"埋食物"的刨地动作和扒地一模一样, 会误报。

### 3. 运行

```bash
# 先带窗口跑, 观察状态判断是否准确 (每路摄像头一个窗口)
python -m watchcat.main --show

# 确认没问题后无界面长期运行
python -m watchcat.main
```

状态流转: `moving`(走动) → `stationary`(静止) → `scratching`(扒地, 橙色)
→ `squatting`(蹲姿, 红色)。手机断流会自动重连, 不用管。

### 4. 调阈值

每次触发都保存在 `events/<房间名>/<时间戳>/`。跑几天后回看:

- **误报多** (玩耍/舔毛被当成扒地): 调高 `scratch_motion_threshold`,
  或 `trigger_on: both` (要求先扒地后蹲下才报警)
- **漏报**: 调低 `scratch_motion_threshold` 或 `scratch_min_seconds`
- **想更早介入**: `trigger_on: scratch` (默认, 扒地就报, 抢在蹲下之前)

**同时记录它换了哪些新作案点** —— 这份"作案热力图"决定二期在哪个房间加手机。

## 测试

行为状态机和配置层是纯 Python, 不装 opencv/YOLO 也能跑:

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
├── main.py       主循环: 多路采集(断流自动重连) -> 检测 -> 分析 -> 警报/录像
├── detector.py   YOLO 猫检测
├── behavior.py   行为状态机 (静止/扒地/蹲姿判定, 纯 Python)
├── alert.py      警报调度: 全局冷却 + 路由到案发房间的手机放声
├── recorder.py   事件录像 (滚动缓冲, 保存触发前后片段)
├── geometry.py   多边形区域判定
└── config.py     配置加载 (单摄像头/多摄像头两种写法)
tools/
├── phone_sound_server.py  手机端放声服务 (Termux 里运行)
├── calibrate_zone.py      鼠标标定猫砂盆区域 (--camera 指定房间)
└── make_beep.py           生成兜底蜂鸣声
docs/
└── product-design.md      两期产品设计 + 终极形态机器人方案
```
