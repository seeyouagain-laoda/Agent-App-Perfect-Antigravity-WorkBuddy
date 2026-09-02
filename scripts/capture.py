# -*- coding: utf-8 -*-
"""
抓取 Antigravity / agy 主窗口截图（PrintWindow 优先，全屏兜底）。
依赖：pywin32, psutil, Pillow。
输出：当前目录 screenshot.png
"""
import win32gui, win32ui, win32con, win32process, psutil, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshot.png")


def find_main():
    cands = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            name = psutil.Process(pid).name().lower()
        except Exception:
            name = ""
        if "antigravity" not in name and "agy" not in name:
            return
        t = win32gui.GetWindowText(hwnd)
        r = win32gui.GetWindowRect(hwnd)
        w, h = r[2] - r[0], r[3] - r[1]
        cands.append((hwnd, t, w * h, w, h, r))

    win32gui.EnumWindows(cb, None)
    main = [c for c in cands if (c[1] == "" or "antigravity" in c[1].lower()) and c[2] > 10000]
    if not main:
        main = [c for c in cands if c[2] > 10000]
    main.sort(key=lambda c: -c[2])
    return main[0] if main else None


m = find_main()
if not m:
    print("NO_WINDOW（请先打开 Antigravity 应用）")
else:
    hwnd, title, area, w, h, r = m
    print("FOUND hwnd=%s title=%r area=%d size=%dx%d rect=%s" % (hwnd, title, area, w, h, r))
    try:
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        bmp = mfcDC.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(bmp)
        res = win32gui.PrintWindow(hwnd, saveDC.GetSafeHdc(), 0)
        bmp.SaveBitmapFile(saveDC, OUT)
        win32gui.ReleaseDC(hwnd, hwndDC)
        print("PRINTWINDOW result=%s SAVED %s" % (res, OUT))
    except Exception as e:
        print("PRINTWINDOW_FAIL", repr(e))
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(OUT)
            print("FALLBACK_FULLSCREEN SAVED", OUT, img.size)
        except Exception as e2:
            print("FALLBACK_FAIL", repr(e2))
