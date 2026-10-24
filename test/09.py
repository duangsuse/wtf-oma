"""HIDDEN state (v2/demo.js state): State 事务 —— 写同值 / 写了又写回不发 patch, 批量写合成一条, c.setTimeout 一次 / 取消 / 重复, 关闭后定时器全清。
每条发给渲染端的 patch 的键写在屏底 "patches=N keys=..."。inspect=1 让每个按键都有可见变化。"""
from tui import *

CMD = f"{DEMO} state inspect=1"


def _00(c):
    """首帧: 还没有 patch"""
    c - [grep, "Same n=0", gone, "patches="]


def _01(c):
    """Same: 写同值, 没有 patch"""
    c - [ENTER, gone, "patches="]


def _02(c):
    """Bounce: n+1 又写回 n(同一事务), 没有 patch"""
    c - [RIGHT, ENTER, gone, "patches="]


def _03(c):
    """Batch: c1({ n, body }) 批量写, 合成一条 patch(body 和依赖 n 的三个标签一起变)"""
    c - [RIGHT, ENTER, grep, "patches=1 keys=body,Same,Bounce,Batch", grep, "batched", grep, "Batch n=1", grep, "Same n=1"]


def _04(c):
    """Once: c.setTimeout(300) 到点写 footer -> 第 2 条 patch"""
    c - [RIGHT, ENTER, wait, 0.6, grep, "timer fired", grep, "patches=2 keys=footer"]


def _05(c):
    """Cancel: 返回的取消函数让定时器不触发, footer 不变、没有新 patch"""
    c - [RIGHT, ENTER, wait, 0.6, gone, "SHOULD NOT", grep, "patches=2 keys=footer"]


def _06(c):
    """Tick 开一个 c.setTimeout(-100) 重复定时器; Done 关闭对话框后它被清掉(不再触发)"""
    c - [RIGHT, ENTER, RIGHT, ENTER, grep, "result: Done", wait, 1.0, grep, r"timers stopped after \w+ ticks"]
