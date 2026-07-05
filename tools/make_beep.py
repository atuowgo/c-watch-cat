"""生成一个默认的警报音 (三声短促高频蜂鸣).

用法: python tools/make_beep.py [输出路径, 默认 sounds/alert.wav]

注意: 蜂鸣声只是兜底方案。对猫最有效的是主人自己的声音 ——
用手机录一段你平时吼它的声音, 转成 wav 后替换 sounds/alert.wav 即可。
"""

import math
import struct
import sys
import wave
from pathlib import Path

RATE = 44100


def tone(freq, seconds, volume=0.9):
    n = int(RATE * seconds)
    fade = int(RATE * 0.01)  # 10ms 淡入淡出防爆音
    samples = []
    for i in range(n):
        amp = volume
        if i < fade:
            amp *= i / fade
        elif i > n - fade:
            amp *= (n - i) / fade
        samples.append(amp * math.sin(2 * math.pi * freq * i / RATE))
    return samples


def silence(seconds):
    return [0.0] * int(RATE * seconds)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sounds/alert.wav")
    out.parent.mkdir(parents=True, exist_ok=True)

    samples = []
    for _ in range(3):
        samples += tone(1400, 0.18)
        samples += silence(0.12)

    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        frames = b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767))
            for s in samples)
        w.writeframes(frames)
    print(f"已生成 {out} ({len(samples) / RATE:.1f} 秒)")
    print("提示: 建议用你自己吼猫的录音替换这个文件, 效果会好得多!")


if __name__ == "__main__":
    main()
