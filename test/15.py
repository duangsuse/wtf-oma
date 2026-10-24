"""按钮底色两端渐隐到 THEME.fadeBg (color.fadeBg=#f00000), 不是黑色; 默认 null 时渐隐到窗口底色 (v2/demo.js dialogs)。"""
from tui import *

CMD = f"{DEMO} dialogs color.fadeBg=#f00000"


def _00(c):
    """选中的 OK 按钮(selBg 082016)左缘一格是 fadeBg 与 selBg 对半混合 7c100b, 紧邻的内侧格是 selBg 本色 082016"""
    c - [grep, "OK", bg_at, "OK", -3, "7c100b", bg_at, "OK", -2, "082016"]
