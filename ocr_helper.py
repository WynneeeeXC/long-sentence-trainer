# -*- coding: utf-8 -*-
"""图片 OCR：调用 Windows 内置 OCR 引擎（WinRT Windows.Media.Ocr），零额外依赖。
用法：ocr_image(图片绝对路径) -> {"ok": True, "text": "..."} 或 {"ok": False, "error": "..."}
"""
import os
import subprocess

_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr", "ocr.ps1")


def ocr_image(path: str) -> dict:
    if not os.path.exists(path):
        return {"ok": False, "error": "图片文件不存在"}
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", _SCRIPT, "-Path", path],
            capture_output=True, text=True, timeout=180,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "OCR 超时（图片可能太大，试试压缩后上传）"}
    except Exception as e:
        return {"ok": False, "error": f"OCR 启动失败：{e}"}
    out = (r.stdout or "").strip()
    if "__NO_OCR_ENGINE__" in out:
        return {"ok": False, "error": "系统没有可用的 OCR 语言引擎（需安装中文/英文语言包）"}
    if "__OCR_ERROR__" in out:
        msg = out.split("__OCR_ERROR__", 1)[1].strip()
        return {"ok": False, "error": f"OCR 失败：{msg}"}
    if r.returncode != 0:
        return {"ok": False, "error": f"OCR 进程异常（{r.returncode}）"}
    text = out.strip()
    if not text:
        return {"ok": False, "error": "没有识别到文字，请确认图片清晰、方向正确"}
    return {"ok": True, "text": text}
