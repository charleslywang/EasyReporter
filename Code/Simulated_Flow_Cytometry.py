# -*- coding: utf-8 -*-
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
import numpy as np
import os
from matplotlib.lines import Line2D
import seaborn as sns
import argparse
import glob
import sys
import io
import math

# 确保在Windows环境下正确处理Unicode字符
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # 兼容旧版本Python
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 设置字体类型与统一颜色（全局），尽量与 Cell_Distribution_Scatter 保持一致
mpl.rcParams['font.family'] = 'DejaVu Sans'
mpl.rcParams['axes.unicode_minus'] = False

# 统一字体颜色（标题、坐标轴、刻度、图例文字）
text_color = 'black'
mpl.rcParams['text.color'] = text_color
mpl.rcParams['axes.labelcolor'] = text_color
mpl.rcParams['xtick.color'] = text_color
mpl.rcParams['ytick.color'] = text_color

# 默认标签文本（图片内文字统一使用英文，避免 DejaVu Sans 无法渲染中文导致方框）
LABELS_ZH = {
    "egfp_label": "GFP",
    "mcherry_label": "mCherry",
    "overlap_label": "Overlap",
    "efficiency_label": "Target Efficiency",
    "title": "Simulated Flow Cytometry",
    "xlabel": "Log10(GFP-MFI)",
    "ylabel": "Log10(mCherry-MFI)"
}

# 英文标签文本
LABELS_EN = {
    "egfp_label": "GFP",
    "mcherry_label": "mCherry",
    "overlap_label": "Overlap",
    "efficiency_label": "Target Efficiency",
    "title": "Simulated Flow Cytometry",
    "xlabel": "Log10(GFP-MFI)",
    "ylabel": "Log10(mCherry-MFI)"
}

# 合并语言字典
LABELS = {
    "zh": LABELS_ZH,
    "en": LABELS_EN
}

# 图例中代表性的三个点（EGFP、mCherry、Overlap）的大小（单位：points）。按需调整即可生效。
legend_marker_sizes = {
    "egfp": 19,
    "mcherry": 19,
    "overlap": 19
}

# 大幅降低渲染像素上限，避免MemoryError
# 对于12x12英寸的图像，10MP意味着最大DPI约263
MAX_RENDER_PIXELS = 10_000_000  # 上限约 10MP，确保在各种系统上稳定


def compute_safe_dpi(figsize, requested_dpi, min_dpi=150):
    """
    根据图像尺寸和像素限制计算安全的DPI
    
    Args:
        figsize: (width, height) 图像尺寸（英寸）
        requested_dpi: 用户请求的DPI
        min_dpi: 最小DPI（降低到150以确保低端系统也能运行）
    
    Returns:
        安全的DPI值
    """
    width_in, height_in = figsize
    if width_in <= 0 or height_in <= 0:
        return max(requested_dpi, min_dpi)

    max_dpi = math.sqrt(MAX_RENDER_PIXELS / (width_in * height_in))
    if math.isnan(max_dpi) or max_dpi <= 0:
        return max(requested_dpi, min_dpi)

    safe_dpi = int(min(requested_dpi, max_dpi))
    if safe_dpi < min_dpi:
        safe_dpi = min_dpi
    
    # 额外检查：确保总像素数不超过限制
    total_pixels = (width_in * safe_dpi) * (height_in * safe_dpi)
    if total_pixels > MAX_RENDER_PIXELS:
        # 如果仍然超过，再次降低DPI
        safe_dpi = int(math.sqrt(MAX_RENDER_PIXELS / (width_in * height_in)) * 0.9)  # 留10%安全边距
        safe_dpi = max(safe_dpi, 100)  # 绝对最小值100 DPI
    
    return safe_dpi


def create_flow_cytometry_plot(csv_file, output_file, lang, colors=None, palette='Set2', point_size=35, figsize=(12, 12), dpi=600):
    # 创建类似流式细胞术的散点图，展示EGFP和mcherry的荧光强度分布（样式参考 Cell_Distribution_Scatter）
    labels = LABELS.get(lang, LABELS["en"])
    # 基于图像尺寸限制实际 DPI，避免生成超大位图导致内存错误
    dpi = int(dpi)
    safe_dpi = compute_safe_dpi(figsize, dpi)
    if safe_dpi < dpi:
        print(f"[SimFlow] Requested DPI {dpi} 降至 {safe_dpi}（图像尺寸 {figsize} 导致像素数过大）")

    df = pd.read_csv(csv_file)

    # 处理缺失值与非正值：缺失替换为非缺失最小值的十分之一；非正值替换为一个小正数，避免对数问题
    min_egfp = df[df['EGFP_MeanIntensity'].notna()]['EGFP_MeanIntensity'].min()
    min_mcherry = df[df['mcherry_MeanIntensity'].notna()]['mcherry_MeanIntensity'].min()
    min_egfp_fill = (min_egfp if pd.notna(min_egfp) else 1.0) / 10.0
    min_mcherry_fill = (min_mcherry if pd.notna(min_mcherry) else 1.0) / 10.0
    df['EGFP_MeanIntensity'] = df['EGFP_MeanIntensity'].fillna(min_egfp_fill)
    df['mcherry_MeanIntensity'] = df['mcherry_MeanIntensity'].fillna(min_mcherry_fill)
    # 将非正值替换为小正值，避免 log10 产生 -inf/NaN
    df.loc[df['EGFP_MeanIntensity'] <= 0, 'EGFP_MeanIntensity'] = max(min_egfp_fill, 1e-6)
    df.loc[df['mcherry_MeanIntensity'] <= 0, 'mcherry_MeanIntensity'] = max(min_mcherry_fill, 1e-6)

    # 取数据列
    egfp = df['EGFP_MeanIntensity']
    mcherry = df['mcherry_MeanIntensity']
    cell_types = df['CellType']

    # 对数转换
    egfp_log = np.log10(egfp)
    mcherry_log = np.log10(mcherry)

    # 设置颜色映射（与 Cell_Distribution_Scatter 使用的三色顺序一致：EGFP、mCherry、Overlap/EGFP+mcherry）
    if colors:
        color_map = {'EGFP': colors[0], 'mcherry': colors[1], 'EGFP+mcherry': colors[2]}
    else:
        palette_colors = sns.color_palette(palette, 3)
        color_map = {label: palette_colors[i] for i, label in enumerate(['EGFP', 'mcherry', 'EGFP+mcherry'])}

    colors_mapped = cell_types.map(color_map).fillna('blue')

    # 创建图形
    fig = plt.figure(figsize=figsize, dpi=safe_dpi)
    ax = plt.gca()
    scatter = plt.scatter(egfp_log, mcherry_log, c=colors_mapped, alpha=0.7, s=point_size)

    # 添加分割线，分别取对应类型的最小值的90%
    # 阈值线（若某一类别不存在则跳过该线）
    try:
        egfp_min = df[df['CellType'] == 'EGFP']['EGFP_MeanIntensity'].min()
        if pd.notna(egfp_min) and egfp_min > 0:
            egfp_threshold = np.log10(egfp_min * 0.9)
            plt.axvline(x=egfp_threshold, color='black', linestyle='--', alpha=0.5)
    except Exception:
        pass
    try:
        mcherry_min = df[df['CellType'] == 'mcherry']['mcherry_MeanIntensity'].min()
        if pd.notna(mcherry_min) and mcherry_min > 0:
            mcherry_threshold = np.log10(mcherry_min * 0.9)
            plt.axhline(y=mcherry_threshold, color='black', linestyle='--', alpha=0.5)
    except Exception:
        pass

    # 统计细胞数量和百分比
    total_cells = len(df)
    counts = df['CellType'].value_counts()
    percentages = (counts / total_cells * 100).round(1)

    # 图例：与 Cell_Distribution_Scatter 一致，底部两行（数量 + 效率）
    count_egfp = int(counts.get('EGFP', 0))
    count_mcherry = int(counts.get('mcherry', 0))
    count_overlap = int(counts.get('EGFP+mcherry', 0))

    # 仅数量标签（EGFP、mCherry、Overlap），靠底部居中一行
    ms_egfp = legend_marker_sizes.get('egfp', max(12, int(point_size * 0.6)))
    ms_mcherry = legend_marker_sizes.get('mcherry', max(12, int(point_size * 0.6)))
    ms_overlap = legend_marker_sizes.get('overlap', max(12, int(point_size * 0.6)))
    count_handles_proxy = [
        Line2D([], [], linestyle='', marker='o', markersize=ms_egfp,
               markerfacecolor=color_map.get('EGFP', '#238C2A'), markeredgecolor=color_map.get('EGFP', '#238C2A')),
        Line2D([], [], linestyle='', marker='o', markersize=ms_mcherry,
               markerfacecolor=color_map.get('mcherry', '#BF0B3B'), markeredgecolor=color_map.get('mcherry', '#BF0B3B')),
        Line2D([], [], linestyle='', marker='o', markersize=ms_overlap,
               markerfacecolor=color_map.get('EGFP+mcherry', '#F2B90C'), markeredgecolor=color_map.get('EGFP+mcherry', '#F2B90C')),
    ]
    count_labels = [
        f"{labels['egfp_label']}: {count_egfp}",
        f"{labels['mcherry_label']}: {count_mcherry}",
        f"{labels['overlap_label']}: {count_overlap}"
    ]
    legend_counts = fig.legend(
        count_handles_proxy, count_labels,
        loc='lower center', bbox_to_anchor=(0.5, 0.08),
        ncol=len(count_labels), fontsize=36,
        frameon=False, fancybox=False, shadow=False,
        columnspacing=1.2, handletextpad=0.3, handlelength=0.0
    )

    # 效率 = EGFP_only / (EGFP_only + Overlap) × 100%（与 Cell_Distribution_Scatter 保持一致；若分母为0则显示 N/A）
    denom = count_egfp + count_overlap
    if denom > 0:
        efficiency_pct = (count_egfp / denom) * 100.0
        efficiency_text = f"{labels['efficiency_label']}: {efficiency_pct:.1f}%"
    else:
        efficiency_text = labels['efficiency_na']
    efficiency_handle = Line2D([], [], linestyle='')
    legend_eff = fig.legend(
        [efficiency_handle], [efficiency_text],
        loc='lower center', bbox_to_anchor=(0.5, 0.0),
        ncol=1, fontsize=36,
        frameon=False, fancybox=False, shadow=False, framealpha=0.90,
        columnspacing=0.8, handletextpad=0.2, handlelength=0.0
    )

    # 统一图例文字颜色
    for leg in [legend_counts, legend_eff]:
        if leg is not None:
            for t in leg.get_texts():
                t.set_color(text_color)

    # 设置标题（从目录名解析，如 Cas9-site11），并统一坐标轴与刻度样式
    title_text = None
    try:
        base_name = os.path.basename(os.path.dirname(csv_file))
        parts = base_name.split('_')
        target_part = parts[2] if len(parts) >= 3 else base_name
        m = __import__('re').search(r"(?i)(cas\d+)-sg(\d+)", target_part)
        if m:
            cas_digits = __import__('re').search(r"(\d+)", m.group(1)).group(1)
            site_digits = m.group(2)
            title_text = f"Cas{cas_digits}-site{site_digits}"
    except Exception:
        title_text = None
    
    # 不再显示标题
    # if title_text:
    #     ax.set_title(title_text, fontsize=36, pad=24, color=text_color)

    # 设置坐标轴标签（保留语义描述，颜色与字号统一）
    plt.xlabel(labels['xlabel'], fontsize=40, color=text_color)
    plt.ylabel(labels['ylabel'], fontsize=40, color=text_color)
    # 保留坐标轴数值标签与刻度，设置字号
    ax.tick_params(axis='both', which='major', labelsize=40)

    # 优化坐标轴范围：不强制对称，根据实际数据分布设置，减少空白
    # X 和 Y 轴独立设置范围，使用实际数据的最小最大值加上小边距
    x_margin = (egfp_log.max() - egfp_log.min()) * 0.05  # 5% 边距
    y_margin = (mcherry_log.max() - mcherry_log.min()) * 0.05
    
    plt.xlim(egfp_log.min() - x_margin, egfp_log.max() + x_margin)
    plt.ylim(mcherry_log.min() - y_margin, mcherry_log.max() + y_margin)
    plt.grid(False)

    # 统一轴与边框颜色
    for spine in ax.spines.values():
        spine.set_color(text_color)

    # 尽量减少左右空白：去除 x 方向数据边距（保持 y 方向少量留白）
    try:
        ax.margins(x=0.0, y=0.02)
    except Exception:
        pass

    # 动态为图例与标题预留空间，避免遮挡，风格与 Cell_Distribution_Scatter 保持一致
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    legend_eff_bbox_in = legend_eff.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
    legend_eff_h_in = legend_eff_bbox_in.height
    legend_counts_h_in = 0.0
    if legend_counts is not None:
        legend_counts_bbox_in = legend_counts.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
        legend_counts_h_in = legend_counts_bbox_in.height
    legend_vgap_in = 0.06
    legend_total_h_in = legend_eff_h_in + legend_counts_h_in + legend_vgap_in

    # 额外测量 X 轴刻度与标签高度，确保底部图例不遮挡
    xtick_h_in = 0.0
    try:
        for tick in ax.get_xticklabels():
            if tick.get_visible():
                bb_in = tick.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
                xtick_h_in = max(xtick_h_in, bb_in.height)
    except Exception:
        pass
    xlabel_h_in = 0.0
    try:
        xl_bb_in = ax.xaxis.label.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
        xlabel_h_in = xl_bb_in.height
    except Exception:
        pass

    fig_w_in, fig_h_in = fig.get_size_inches()
    padding_bottom_in = 0.12
    # 轴标签与数量图例之间的额外间距，避免两者紧挨
    axes_to_legend_gap_in = 0.42
    bottom_margin = (legend_total_h_in + xtick_h_in + xlabel_h_in + padding_bottom_in + axes_to_legend_gap_in) / fig_h_in
    bottom_margin = max(bottom_margin, 0.12)
    bottom_margin = min(bottom_margin, 0.50)

    # 顶部边距（考虑标题高度）
    title_h_in = 0.0
    try:
        if ax.title and ax.title.get_text():
            t_bb_in = ax.title.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
            title_h_in = t_bb_in.height
    except Exception:
        pass
    padding_top_in = 0.06
    top_margin = (title_h_in + padding_top_in) / fig_h_in
    top_frac = 1.0 - max(min(top_margin, 0.15), 0.02)

    # 左右边距（考虑 Y 轴刻度与标签宽度，避免裁切）
    ytick_w_in = 0.0
    try:
        for tick in ax.get_yticklabels():
            if tick.get_visible():
                bb_in = tick.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
                ytick_w_in = max(ytick_w_in, bb_in.width)
    except Exception:
        pass
    ylabel_w_in = 0.0
    try:
        yl_bb_in = ax.yaxis.label.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
        ylabel_w_in = yl_bb_in.width
    except Exception:
        pass
    padding_left_in = 0.06
    left_margin = (ytick_w_in + ylabel_w_in + padding_left_in) / fig_w_in
    left_margin = max(left_margin, 0.05)
    left_margin = min(left_margin, 0.30)
    right_frac = 1.0 - left_margin

    fig.subplots_adjust(left=left_margin, right=right_frac, top=top_frac, bottom=bottom_margin)

    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # 保存图像为png和pdf格式 - 移除 bbox_inches='tight' 以严格使用用户设置的 figsize
    try:
        plt.savefig(f"{output_file}.png", dpi=safe_dpi)
        plt.savefig(f"{output_file}.pdf", dpi=safe_dpi)
    finally:
        # 强制清理图形和释放内存
        plt.close(fig)
        plt.close('all')
        # 清理内存（强制垃圾回收）
        import gc
        gc.collect()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="批量生成流式细胞术风格散点图（样式与 Cell_Distribution_Scatter 保持一致）")
    parser.add_argument('--input', '-i', required=True, help='输入文件夹，支持递归查找csv')
    parser.add_argument('--output', '-o', required=True, help='输出文件夹')
    parser.add_argument('--colors', '-c', nargs=3, help='颜色列表，例如 "#238C2A" "#BF0B3B" "#F2B90C"')
    parser.add_argument('--point_size', '-p', type=int, default=35, help='点大小，默认35')
    parser.add_argument('--figsize', '-f', nargs=2, type=float, default=[12, 12], help='图像尺寸，默认12 12')
    parser.add_argument('--dpi', type=int, default=600, help='渲染 DPI，默认 600，过大时会自动降级')
    parser.add_argument("--lang", type=str, default="en", choices=["zh", "en"], help="Language for labels (zh or en)")

    args = parser.parse_args()

    input_folder = os.path.abspath(args.input)
    output_folder = os.path.abspath(args.output)
    colors = args.colors
    point_size = args.point_size
    figsize = tuple(args.figsize)
    dpi = args.dpi
    lang = args.lang

    # 递归查找所有csv文件
    csv_files = glob.glob(os.path.join(input_folder, '**', '*.csv'), recursive=True)

    if not csv_files:
        print(f"未在目录 {input_folder} 及其子目录中找到任何csv文件。")
        exit(1)

    for csv_file in csv_files:
        # 计算相对路径（相对于输入目录）
        relative_path = os.path.relpath(csv_file, input_folder)
        # 去掉文件扩展名
        relative_path_no_ext = os.path.splitext(relative_path)[0]
        # 构建输出路径，保持目录结构
        output_file = os.path.join(output_folder, relative_path_no_ext)
        create_flow_cytometry_plot(
            csv_file,
            output_file,
            lang,
            colors=colors,
            point_size=point_size,
            figsize=figsize,
            dpi=dpi,
        )

    print(f"全部绘图完成，共生成 {len(csv_files)} 张图，保存在：{output_folder}")

