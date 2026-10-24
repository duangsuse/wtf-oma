"""pi.inlineKbd (v2/demo.js kbd): 输入框上方的窄下拉 -- 打字过滤(子序列) / Tab ↑↓ 选择 / Enter 给选中项 / Esc 给 null。"""
from tui import *

CMD = f"{DEMO} kbd"


def _00(c):
    """列表出现: 最多 kbdRows(5) 行, 前 5 项在、第 6 项 /compact 起不在; 计数 8/8, 提示符 '> '"""
    c - [grep, "/model", grep, "/help", grep, "/clear", gone, "/compact", grep, r"8/8", grep, r"> "]


def _01(c):
    """打 'co': 只留子序列匹配的 /compact /config /cost, 计数 3/8"""
    c - [paste("co"), grep, r"3/8", grep, "/compact", grep, "/config", grep, "/cost", gone, "/model", gone, "/help"]


def _02(c):
    """Tab Tab Enter: 过滤后第一项 /compact 起, 选到第三项 /cost; resolve 为 '/cost'"""
    c - [TAB, TAB, ENTER, grep, "result: /cost"]


def _03(c):
    """第二次: Esc 取消 -> null"""
    c - [ESC, grep, "result: null"]
