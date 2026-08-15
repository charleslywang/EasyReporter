#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立 HTML → PDF 渲染脚本
使用系统自带的 Microsoft Edge (Chromium) 无头模式将 HTML 打印为 PDF，
完美保留 CSS 样式、图片、布局，效果等同于浏览器"打印为 PDF"。

用法:
    python pdf_renderer.py <input_html_path> <output_pdf_path>
    
依赖:
    - Windows 10+: 系统自带 Microsoft Edge
    - macOS: 系统自带 Safari/Chrome 可用
    - Linux: 需要安装 chromium-browser 或 google-chrome
"""

import os
import sys
import subprocess
import shutil
import tempfile


def find_browser():
    """查找系统可用的无头浏览器"""
    if sys.platform.startswith('win'):
        # Windows: 优先使用 Edge (系统自带), 其次 Chrome
        candidates = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        # 尝试 PATH 查找
        for name in ['msedge', 'microsoft-edge', 'chrome', 'chromium']:
            found = shutil.which(name)
            if found:
                return found
    elif sys.platform.startswith('darwin'):
        candidates = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        for name in ['google-chrome', 'chromium', 'microsoft-edge']:
            found = shutil.which(name)
            if found:
                return found
    else:  # Linux
        for name in ['google-chrome', 'chromium', 'chromium-browser', 'microsoft-edge']:
            found = shutil.which(name)
            if found:
                return found

    return None


def html_to_pdf(html_path: str, pdf_path: str, browser_exe: str = None,
                virtual_time_budget: int = 15000, timeout: int = 120):
    """
    使用无头浏览器将 HTML 文件转换为 PDF。

    Args:
        html_path: 输入 HTML 文件路径
        pdf_path: 输出 PDF 文件路径
        browser_exe: 浏览器可执行文件路径，为 None 时自动查找
        virtual_time_budget: 虚拟时间预算(ms)，给 JS 执行留时间
        timeout: 子进程超时时间(秒)

    Returns:
        str: 成功时返回 pdf_path

    Raises:
        RuntimeError: 浏览器未找到或转换失败
    """
    if browser_exe is None:
        browser_exe = find_browser()

    if browser_exe is None:
        raise RuntimeError(
            "未找到可用的无头浏览器。\n"
            "Windows: 系统自带 Microsoft Edge，无需额外安装。\n"
            "macOS: 请安装 Google Chrome 或 Microsoft Edge。\n"
            "Linux: 请安装 chromium-browser 或 google-chrome。"
        )

    # 确保 HTML 文件存在
    if not os.path.exists(html_path):
        raise FileNotFoundError(f"HTML 文件不存在: {html_path}")

    # 确保输出目录存在
    os.makedirs(os.path.dirname(pdf_path) or '.', exist_ok=True)

    # 构建 file:// URL
    html_url = f"file:///{html_path.replace(os.sep, '/')}"

    # 构建命令行参数
    cmd = [
        browser_exe,
        '--headless',                    # 无头模式
        '--disable-gpu',                 # 禁用 GPU（无头模式必需）
        '--no-sandbox',                  # 部分环境需要
        '--disable-software-rasterizer',
        f'--print-to-pdf={pdf_path}',    # 输出 PDF
        '--no-pdf-header-footer',        # 不添加页眉页脚
        f'--virtual-time-budget={virtual_time_budget}',  # JS 执行时间
        html_url,
    ]

    # 执行命令
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=timeout,
        )

        if result.returncode != 0:
            stderr_msg = result.stderr[:500] if result.stderr else "(无错误输出)"
            raise RuntimeError(
                f"浏览器进程返回错误码 {result.returncode}。\n"
                f"stderr: {stderr_msg}"
            )

        # 验证输出文件
        if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0:
            raise RuntimeError("PDF 文件未生成或为空")

        return pdf_path

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"HTML 转 PDF 超时（{timeout}秒），请检查 HTML 文件大小")
    except FileNotFoundError:
        raise RuntimeError(f"找不到浏览器可执行文件: {browser_exe}")


def main():
    """命令行入口"""
    if len(sys.argv) < 3:
        print(__doc__)
        print("用法: python pdf_renderer.py <input_html> <output_pdf>")
        sys.exit(1)

    html_path = sys.argv[1]
    pdf_path = sys.argv[2]

    print(f"[pdf_renderer] 输入 HTML: {html_path}")
    print(f"[pdf_renderer] 输出 PDF:  {pdf_path}")

    browser = find_browser()
    print(f"[pdf_renderer] 使用浏览器: {browser}")

    try:
        result = html_to_pdf(html_path, pdf_path, browser_exe=browser)
        print(f"[pdf_renderer] ✅ PDF 生成成功: {result}")
        sys.exit(0)
    except Exception as e:
        print(f"[pdf_renderer] ❌ PDF 生成失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
