"""HIDDEN notify (v2/demo.js notify): 角标变体 + dialog.ret() 无参 + pi.if404 直接用。"""
from tui import *

CMD = f"{DEMO} notify"


def _00(c):
    """snack 在右上, snackRD 在右下; 默认底色是强调色, bg 'none' 没有底色; 没有 where 的 notify 不画角标"""
    c - [grep, "top-right default", corner, "top-right", "top", corner, "bottom-right plain", "bottom",
         bg_is, "top-right default", "1f8c1f", bg_is, "bottom-right plain", "default", gone, "desktop only"]


def _01(c):
    """Theme: setTheme({ snackBg }) 之后, 已经在屏上的默认底色角标立即跟着变(snackBg 不是创建角标时的快照)"""
    c - [ENTER, bg_is, "top-right default", "3050e0"]


def _02(c):
    """Red: bg '#e03030' 替换右上角标(同一角一条)"""
    c - [RIGHT, ENTER, grep, "red snack", gone, "top-right default", bg_is, "red snack", "e03030"]


def _03(c):
    """Num: bg 0x2030e0(数字按 0xRRGGBB)替换右下角标"""
    c - [RIGHT, ENTER, grep, "num snack", gone, "bottom-right plain", bg_is, "num snack", "2030e0"]


def _04(c):
    """Clear: notify('') 撤下两个角标"""
    c - [RIGHT, ENTER, gone, "red snack", gone, "num snack"]


def _05(c):
    """Done 后 ret() 无参关闭 -> null; if404 直接用: 登记的 a、没登记的 zzz、then 不被当作 thenable"""
    c - [RIGHT, ENTER, grep, "result: Done", grep, r"ret\(\)", wait, 1.0, grep, "result: null A nf:zzz undefined"]
