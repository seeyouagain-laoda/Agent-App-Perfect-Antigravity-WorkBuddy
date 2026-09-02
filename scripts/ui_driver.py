# -*- coding: utf-8 -*-
"""
ui_driver.py（v7 — 驱动【官方 Antigravity 应用】输入框，非驾驶舱）

工作流：
1) 本脚本在你真机桌面会话常驻运行（双击桌面的 agy_ui_driver.bat 启动）。
2) WorkBuddy 对话侧把任务写到同目录 inbox.txt（沙箱 -> 真机文件系统通道）。
3) 本脚本读 inbox -> 聚焦官方 Antigravity 应用主窗 -> 把任务键入底部输入框 -> 回车提交。
4) 官方应用窗口实时显示它的思考链和回答（你直接看，无第三方界面）。
5) 提交记录写 outbox.txt。

v7 修复（基于 status.txt 实锤的失控日志）：
- 启动即杀掉旧 ui_driver 实例（不再依赖已移除的 wmic），避免双击出双份抢 inbox / 单例退出。
- find_app 不再丢弃 area=0 的空标题主窗（Electron 主窗常空标题且被量到 0），优先选它。
- 输入框定位优先用 UI Automation 找真正的可编辑控件（Edit/Document），找不到才退回窗口相对坐标。
- 全局异常钩子：任何未捕获异常写入 status.txt，黑窗口也看得到，不再静默崩溃丢失信息。
- 找不到应用时任务存内存 pending，8 秒重试一次，不再每 3 秒刷屏重写 inbox。

关键限制（已实测）：
- WorkBuddy 沙箱发不出键鼠事件（SendInput 被拦），键入必须由【你真机桌面会话】里的
  本脚本完成。沙箱只负责把任务写进 inbox.txt（文件系统通道，可用）。
- 官方应用需你先手动打开并登录 Google 账号（按你的规矩，这步我来不了）。
"""
import os, sys, time, pathlib, traceback

BASE = pathlib.Path(__file__).resolve().parent
INBOX = BASE / "inbox.txt"
OUTBOX = BASE / "outbox.txt"
STATUS = BASE / "status.txt"

# ---------- 定位配置（可经环境变量覆盖，无需改代码） ----------
# 输入框相对窗口的偏移（默认：底部中央上方一点）。可通过环境变量覆盖。
REL_X_RATIO = float(os.environ.get("AGY_INPUT_REL_X", "0.5"))
REL_BOTTOM_OFFSET = int(os.environ.get("AGY_INPUT_REL_Y", "70"))


def log(msg):
    try:
        with open(STATUS, "a", encoding="utf-8", errors="ignore") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg) + "\n")
    except Exception:
        pass


# 全局异常钩子：任何未捕获异常都写进 status.txt，便于排查（bat 的 pause 也能看到）
def _exchook(et, ev, tb):
    try:
        log("FATAL: " + "".join(traceback.format_exception(et, ev, tb))[-3000:])
    except Exception:
        pass


sys.excepthook = _exchook


def read_task():
    """原子读取完整任务。读出全部 -> 删除。失败返回 None。"""
    if not INBOX.exists():
        return None
    try:
        text = INBOX.read_text(encoding="utf-8", errors="ignore")
        if not text.strip():
            INBOX.unlink(missing_ok=True)
            return None
        INBOX.unlink(missing_ok=True)
        return text.strip()
    except FileNotFoundError:
        return None
    except Exception as e:
        log(f"read_task err: {e}")
        return None


def force_foreground(hwnd):
    """用 Win32 API 强制把窗口置顶到前台（绕过 Focus Stealing Prevention）。"""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SwitchToThisWindow(hwnd, True)
        time.sleep(0.3)
        return True
    except Exception as e:
        log(f"force_foreground err: {e}")
        return False


def _wins_of(pid):
    """返回某 pid 的所有顶层窗口 [(w, hwnd, title, area, backend, pid)]。win32 优先，uia 兜底。"""
    from pywinauto import Application
    out = []
    for backend in ("win32", "uia"):
        try:
            app = Application(backend=backend).connect(process=pid, timeout=3)
            for w in app.windows():
                try:
                    t = w.window_text()
                    r = w.rectangle()
                    area = max(0, (r.right - r.left) * (r.bottom - r.top))
                    out.append((w, w.handle, t, area, backend, pid))
                except Exception:
                    pass
        except Exception:
            pass
    return out


def find_app():
    """精准定位官方应用主窗口。返回 (w, hwnd, pid, backend) 或 None。

    选窗策略：优先“标题为空 / 含 antigravity / 含实时工作台”的窗（Electron 主窗常空标题，
    且可能被量到 area=0，不再丢弃），其次按面积取最大。
    """
    try:
        import psutil
        pids = []
        for p in psutil.process_iter(["pid", "name", "exe"]):
            try:
                nm = (p.info.get("name") or "").lower()
                ex = (p.info.get("exe") or "").lower()
                if "antigravity" in nm or "antigravity" in ex:
                    pids.append(p.info["pid"])
            except Exception:
                pass
        if not pids:
            log("find_app: 无 Antigravity 进程（请先打开应用并登录）")
            return None

        cands = []
        for pid in pids:
            cands.extend(_wins_of(pid))
        if not cands:
            log("find_app: 进程存在但无可见窗口")
            return None

        for c in cands:
            log(f"  cand title={c[2]!r} hwnd={c[1]} area={c[3]} backend={c[4]}")

        def _score(c):
            t = (c[2] or "").lower()
            is_main = (t == "" or "antigravity" in t or "实时工作台" in t)
            return (0 if is_main else 1, -c[3])  # 主窗优先；主窗之间面积大优先

        cands.sort(key=_score)
        w, hwnd, title, area, backend, pid = cands[0]
        log(f"find_app -> 主窗 title={title!r} hwnd={hwnd} area={area} backend={backend}")
        return w, hwnd, pid, backend
    except Exception as e:
        log(f"find_app err: {e}")
        return None


def find_input_box(w):
    """在选中窗内找可编辑输入框控件（优先 uia）。返回控件或 None。"""
    try:
        from pywinauto import Application
        app = Application(backend="uia").connect(handle=w.handle, timeout=3)
        dlg = app.window(handle=w.handle)
        for ctype in ("Edit", "Document"):
            try:
                boxes = dlg.children(control_type=ctype)
                if boxes:
                    boxes.sort(key=lambda b: b.rectangle().bottom)
                    return boxes[-1]  # 取最靠下的（输入框通常在底部）
            except Exception:
                pass
        try:
            boxes = dlg.descendants(control_type="Edit")
            if boxes:
                return boxes[-1]
        except Exception:
            pass
    except Exception as e:
        log(f"find_input_box err: {e}")
    return None


def submit(task):
    """聚焦官方应用 -> 点输入框 -> 键入任务 -> 回车。控件优先，坐标兜底。"""
    from pywinauto import mouse, keyboard
    import pyperclip

    res = find_app()
    if res is None:
        return False
    w, hwnd, pid, backend = res

    try:
        if w.is_minimized():
            w.restore()
    except Exception:
        pass
    force_foreground(hwnd)
    try:
        w.set_focus()
    except Exception as e:
        log(f"set_focus err: {e}")
    time.sleep(0.5)

    # 优先用 UI 控件定位输入框
    box = find_input_box(w)
    if box is not None:
        try:
            box.click_input()
            time.sleep(0.3)
            box.type_keys("^a")
            time.sleep(0.1)
            pyperclip.copy(task)
            time.sleep(0.25)
            box.type_keys("^v")
            time.sleep(0.6)
            # 兜底：ASCII 且粘贴未生效则逐字键入
            cur = pyperclip.paste()
            if cur.strip() != task.strip() and task.isascii():
                box.type_keys(task, with_spaces=True, pause=0.03)
                time.sleep(0.5)
            box.type_keys("{ENTER}")
            time.sleep(0.8)
            log(f"SUBMITTED_OK(控件) len={len(task)}")
            return True
        except Exception as e:
            log(f"box submit err: {e} -> 退回坐标")

    # 退回窗口相对坐标
    try:
        r = w.rectangle()
        in_x = r.left + int(r.width() * REL_X_RATIO)
        in_y = r.bottom - REL_BOTTOM_OFFSET
    except Exception:
        in_x, in_y = 480, 1035
    mouse.click(coords=(in_x, in_y))
    time.sleep(0.4)
    mouse.click(coords=(in_x, in_y))
    time.sleep(0.3)
    keyboard.send_keys("^a")
    time.sleep(0.15)
    pyperclip.copy(task)
    time.sleep(0.25)
    keyboard.send_keys("^v")
    time.sleep(0.6)
    cur = pyperclip.paste()
    if cur.strip() != task.strip() and task.isascii():
        keyboard.send_keys(task, with_spaces=True, pause=0.03)
        time.sleep(0.5)
    keyboard.send_keys("{ENTER}")
    time.sleep(0.8)
    log(f"SUBMITTED_OK(坐标) len={len(task)}")
    return True


def write_outbox(task):
    try:
        with open(OUTBOX, "a", encoding="utf-8", errors="ignore") as f:
            f.write(f"---\n{time.strftime('%Y-%m-%d %H:%M:%S')}\nTASK: {task}\n")
    except Exception:
        pass


def kill_other():
    """启动时杀掉其它 ui_driver 实例（替代已移除的 wmic），确保新实例能常驻。"""
    if os.environ.get("AGY_NO_KILL"):
        log("kill_other skipped (AGY_NO_KILL set)")
        return
    try:
        import psutil
        # 用 psutil 自身的 pid 作为 me（与 process_iter 同源），避免 PID namespace
        # 下 os.getpid() 与 psutil 枚举到的宿主 pid 不一致导致误杀自己。
        me = psutil.Process().pid
        for p in psutil.process_iter(["pid", "cmdline"]):
            try:
                if p.info["pid"] == me:
                    continue
                cl = " ".join(p.info.get("cmdline") or [])
                if "ui_driver.py" in cl and "ui_driver_v2" not in cl:
                    psutil.Process(p.info["pid"]).kill()
                    log(f"KILL_OLD pid={p.info['pid']}")
            except Exception:
                pass
    except Exception:
        pass


def main():
    kill_other()
    log(f"UI_DRIVER_V7_START pid={os.getpid()}")

    pending = None
    last_note = ""
    while True:
        if pending is None:
            task = read_task()
            if not task:
                time.sleep(0.8)
                continue
            pending = task
            log(f"TASK len={len(task)} preview={task[:50]!r}")

        try:
            ok = submit(pending)
        except Exception as e:
            log(f"submit crash: {e}")
            ok = False

        if ok:
            write_outbox(pending)
            log("TASK_DONE")
            pending = None
            time.sleep(0.3)
        else:
            note = "OFFICIAL_APP_NOT_FOUND -> 等待应用打开(8s)"
            if note != last_note:
                log(note)
                last_note = note
            time.sleep(8)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
        ok = submit(task)
        print("SUBMITTED" if ok else "APP_NOT_FOUND")
    else:
        main()
