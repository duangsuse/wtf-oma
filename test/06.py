"""HIDDEN async (v2/demo.js async): Button 返回 Promise / 渲染时 Promise 标签 / 按钮抛错。"""
from tui import *

CMD = f"{DEMO} async"


def _00(c):
    """渲染时返回 Promise: 先显示键名 Label, 300ms 后标签变成 'late label'"""
    c - [grep, "calls: 0", grep, "Label", wait, 0.6, grep, "late label", gone, "Label"]


def _01(c):
    """按钮返回 Promise: 等待期间不响应第二次按下(连按两次只算一次); 等 resolve 后标签变成 'Slow ✓', 对话框仍开着"""
    c - ["\r\r", grep, "calls: 1", wait, 1.2, grep, "Slow ✓", grep, "calls: 1"]


def _02(c):
    """按钮抛错: 只记日志(屏底 log: ...), 对话框不关"""
    c - [RIGHT, RIGHT, ENTER, grep, "log: dialog button threw Error: boom", grep, "Boom"]


def _03(c):
    """返回已 resolve 的 Promise<undefined> 的按钮: await 之后关闭, resolve 键名"""
    c - [RIGHT, ENTER, grep, "result: Done", gone, "Slow"]
