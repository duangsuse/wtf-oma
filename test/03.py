"""pi.dialog 的 timeout / or (v2/demo.js timeout): 非模态, 右上角, 到点按下选中的按钮, 正文末尾 '(Ns)' 倒计时。"""
from tui import *

CMD = f"{DEMO} timeout"


def _00(c):
    """首帧: 对话框在右上角, 正文 'Delete everything? (2s)'"""
    c - [grep, r"Delete everything\? \(2s\)", upper_right, "with or"]


def _01(c):
    """过 1.3s: 倒计时变成 (1s)"""
    c - [wait, 1.3, grep, r"\(1s\)"]


def _02(c):
    """到点: or='No' 被按下 -> 'result: No'; 下一个对话框(no or)出现"""
    c - [wait, 1.2, grep, "result: No", grep, "no or", grep, r"\(\ds\)"]


def _03(c):
    """没有 or 且没动过: 到点 resolve null"""
    c - [wait, 2.3, grep, "result: null", grep, "touched"]


def _04(c):
    """第一次交互(→)就取消自动选择: 倒计时撤掉, 过了很久对话框还在、不自动按; 手动 Enter 按下选中的 No"""
    c - [RIGHT, gone, r"\(\ds\)", wait, 2.6, grep, "Delete everything", grep, "result: null",
         ENTER, grep, "result: No", gone, "Delete everything"]
