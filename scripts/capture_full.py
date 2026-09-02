# -*- coding: utf-8 -*-
"""
全屏截图（用于诊断/验证本机桌面可见性）。
依赖：Pillow（ImageGrab）；兜底用 pywin32 抓指定进程窗口。
输出：当前目录 desktop_proof.png
"""
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktop_proof.png")


def grab_fullscreen():
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.save(OUT)
        print("FULLSCREEN_OK", img.size, OUT)
        return True
    except Exception as e:
        print("PIL_FAIL", repr(e))
    try:
        import win32gui, win32ui, win32process, psutil
        target = None

        def cb(hwnd, _):
            nonlocal target
            if not win32gui.IsWindowVisible(hwnd):
                return
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                n = psutil.Process(pid).name().lower()
            except Exception:
                n = ""
            if n == "workbuddy.exe":
                r = win32gui.GetWindowRect(hwnd)
                if (r[2] - r[0]) > 300:
                    target = (hwnd, r)

        win32gui.EnumWindows(cb, None)
        if target:
            hwnd, r = target
            w, h = r[2] - r[0], r[3] - r[1]
            hwndDC = win32gui.GetWindowDC(hwnd)
            mfc = win32ui.CreateDCFromHandle(hwndDC)
            save = mfc.CreateCompatibleDC()
            bmp = mfc.CreateCompatibleBitmap(mfc, w, h)
            save.SelectObject(bmp)
            win32gui.PrintWindow(hwnd, save.GetSafeHdc(), 0)
            bmp.SaveBitmapFile(save, OUT)
            win32gui.ReleaseDC(hwnd, hwndDC)
            print("WORKBUDDY_WINDOW_OK", (w, h), OUT)
            return True
    except Exception as e:
        print("FALLBACK_FAIL", repr(e))
    return False


grab_fullscreen()
