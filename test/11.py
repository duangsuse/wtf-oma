"""demo.js 无参启动: inspect 打开(屏底滚动显示线上消息), 场景菜单只列 SCENARIOS 不列 HIDDEN, Node DevTools 固定 9229(被占就不开)。"""
import socket
from tui import *

CMD = DEMO


def devtools_port_free():
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", 9229))
            return True
        except OSError:
            return False


FREE = devtools_port_free()      # 在 demo 启动之前量: 启动后 9229 就是它自己占的


def _00(c):
    """场景菜单列出 dialogs / timeout / focus / omarchy, 不列隐藏场景; 屏底有 → open 日志"""
    c - [grep, "oma demo", grep, "dialogs", grep, "omarchy", gone, r"async|update|layout|state|notify", grep, r"→ open #1"]


def _01(c):
    """DevTools: 9229 空闲时正文给出 127.0.0.1:9229; 被占用就不开、正文里没有这一行"""
    c - ([grep, r"DevTools: 127\.0\.0\.1:9229"] if FREE else [gone, "DevTools:"])


def _02(c):
    """↓ Enter 选 timeout: 日志依次出现 ← press / → close / → open(下一个对话框)"""
    c - [DOWN, ENTER, grep, r"← press #1 timeout", grep, r"→ close #1", grep, r"→ open #2"]
