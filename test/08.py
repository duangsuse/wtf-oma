"""HIDDEN layout (v2/demo.js layout): 无标题 / vertical / 勾选单选语法 / CJK / fadeX 0 / 点击; eachRow [1, 2] 的列对齐与 ↑↓ 保持列(含环绕)。"""
from tui import *

CMD = f"{DEMO} layout"


def _00(c):
    """无标题对话框: 多行正文 + footer; 勾选/单选语法 '( )' '(*)' '[x]' 渲染成图标, 普通按钮没有图标; vertical 时图标后的文字同列(含 CJK)"""
    c - [grep, "line one", grep, "第二行", grep, "footer",
         grep, RAD_OFF + " 中文按钮", grep, RAD_ON + " Go", grep, CHK_ON + " strict", gone, r"\( \)|\(\*\)|\[x\]",
         aligned, "中文按钮", "Go", aligned, "Go", "strict"]


def _01(c):
    """fadeX 0: 按钮底色两端不渐隐(边缘格与右邻同色)"""
    c - [flat, "plain text", -1]


def _02(c):
    """点击 strict: 选中并按下, 返回的文字把它切成关闭的勾选"""
    c - [click, "strict", 0, 0, grep, CHK_OFF + " strict"]


def _03(c):
    """↓ ↓ 到 Quit, Enter: resolve 'Quit'; 下一个对话框 eachRow [1, 2]"""
    c - [DOWN, DOWN, ENTER, grep, "result: Quit", grep, r"rows \[1, 2\]"]


def _04(c):
    """eachRow [1, 2]: 第 1 行 1 个, 之后每行 2 个(最后一个数字重复), 列对齐; 默认 gap 1 对纵向也有效: 相邻两行之间空 1 行"""
    c - [aligned, "b1", "b2", aligned, "b2", "b4", aligned, "b3", "b5", below, "b1", "b2", 2, below, "b2", "b4", 2]


def _05(c):
    """↓ 保持列并环绕: b1→b2→b4, →b5, ↓ 环绕回第 1 行(只有 1 列, 取行尾 b1), ↑ 环绕到最后一行 b4, → b5, ↑ b3, Enter 得 'b3'"""
    c - [DOWN, DOWN, RIGHT, DOWN, UP, RIGHT, UP, ENTER, grep, "result: b3"]
