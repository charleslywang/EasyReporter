# -*- coding: utf-8 -*-
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
import argparse
import re
import sys
import io

# 确保在Windows环境下正确处理Unicode字符
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # 兼容旧版本Python
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 设置字体类型（全局）
mpl.rcParams['font.family'] = 'DejaVu Sans'
mpl.rcParams['axes.unicode_minus'] = False
text_color = 'black'
mpl.rcParams['text.color'] = text_color
mpl.rcParams['axes.labelcolor'] = text_color
mpl.rcParams['xtick.color'] = text_color
mpl.rcParams['ytick.color'] = text_color

# 国际化标签
LABELS_EN = {
    "egfp_label": "GFP",
    "mcherry_label": "mCherry",
    "overlap_label": "Overlap",
    "efficiency_label": "Target Efficiency",
    "efficiency_na": "Target Efficiency: N/A",
}

LABELS = {
    "en": LABELS_EN,
    "zh": LABELS_EN.copy(),
}

def process_and_plot_csv(input_csv, input_root, output_root, colors, figsize, point_size, lang):
    """
    处理单个 CSV 文件，生成转换数据并绘制图像，保持完整目录结构。
    """
    try:
        labels = LABELS.get(lang, LABELS["en"])
        df = pd.read_csv(input_csv)

        if not {'CellType', 'CenterX', 'CenterY'}.issubset(df.columns):
            return False

        # 将原来的 "EGFP+mcherry" 统一改为 "Overlap"（同时兼容旧标签）
        quadrant_mapping = {
            'Overlap': (1, 1),
            'EGFP+mcherry': (1, 1),  # 兼容旧数据中使用的标签
            'EGFP': (-1, 1),
            'mcherry': (-1, -1)
        }

        df['Transformed_X'] = df['CenterX'] * df['CellType'].map(quadrant_mapping).str[0]
        df['Transformed_Y'] = df['CenterY'] * df['CellType'].map(quadrant_mapping).str[1]

        relative_path = os.path.relpath(input_csv, input_root)
        output_csv_path = os.path.join(output_root, relative_path)
        output_img_base = output_csv_path.replace('.csv', '_plot')

        os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
        df.to_csv(output_csv_path, index=False)

        plt.figure(figsize=figsize)
        # 只绘制散点，不显示任何标签
        for cell_type, group in df.groupby('CellType'):
            plt.scatter(group['Transformed_X'], group['Transformed_Y'],
                        color=colors.get(cell_type, 'gray'),
                        alpha=1.0, s=point_size)

        plt.axhline(0, color='black', linewidth=0.8)
        plt.axvline(0, color='black', linewidth=0.8)

        plt.xlabel('')
        plt.ylabel('')
        ax = plt.gca()
        # 统一去除刻度与标签，避免与底部图例干扰并减少无用空白
        ax.set_xticks([])
        ax.set_yticks([])
        ax.tick_params(bottom=False, labelbottom=False, left=False, labelleft=False)
        plt.grid(False)

        # 优化坐标轴范围：不强制对称，根据实际数据分布设置
        # 计算每个方向的实际数据范围
        x_min, x_max = df['Transformed_X'].min(), df['Transformed_X'].max()
        y_min, y_max = df['Transformed_Y'].min(), df['Transformed_Y'].max()
        
        # 添加5%边距，但不强制对称
        x_range = x_max - x_min
        y_range = y_max - y_min
        margin = 0.05
        
        ax.set_xlim(x_min - x_range * margin, x_max + x_range * margin)
        ax.set_ylim(y_min - y_range * margin, y_max + y_range * margin)

        # ===== 底部图例：只显示数量（不含类别文字）+ 效率 =====
        # 尽量收紧数据边距，减少左右额外空白
        try:
            ax.margins(x=0.0, y=0.02)
        except Exception:
            pass

        # 统计数量（仅按三类：EGFP、mcherry、EGFP+mcherry）
        count_egfp = int((df['CellType'] == 'EGFP').sum())
        count_mcherry = int((df['CellType'] == 'mcherry').sum())
        # 统计 Overlap，兼容两种标签写法
        count_overlap = int(((df['CellType'] == 'EGFP+mcherry') | (df['CellType'] == 'Overlap')).sum())

        # 构造“数量图例”代理句柄，标签为类别+数量
        markersize = max(12, int(point_size * 0.6))  # 图例点大小与散点大小相关联，便于在大字号下更明显
        count_handles_proxy = [
            mpl.lines.Line2D([], [], linestyle='', marker='o',
                              markersize=markersize,
                              markerfacecolor=colors.get('EGFP', '#238C2A'),
                              markeredgecolor=colors.get('EGFP', '#238C2A')),
            mpl.lines.Line2D([], [], linestyle='', marker='o',
                              markersize=markersize,
                              markerfacecolor=colors.get('mcherry', '#8B0000'),
                              markeredgecolor=colors.get('mcherry', '#8B0000')),
            mpl.lines.Line2D([], [], linestyle='', marker='o',
                              markersize=markersize,
                              markerfacecolor=colors.get('Overlap', '#F2B90C'),
                              markeredgecolor=colors.get('Overlap', '#F2B90C')),
        ]
        count_labels = [
            f"{labels['egfp_label']}: {count_egfp}",
            f"{labels['mcherry_label']}: {count_mcherry}",
            f"{labels['overlap_label']}: {count_overlap}"
        ]

        # 使用 Axes 级 legend 并启用 expand，使左右与散点图边框对齐
        fig = plt.gcf()
        legend_counts = fig.legend(
            count_handles_proxy, count_labels,
            loc='lower center',
            bbox_to_anchor=(0.5, 0.08),
            ncol=len(count_labels),
            fontsize=36,
            frameon=False, fancybox=False, shadow=False,
            columnspacing=1.2,
            handletextpad=0.3,
            handlelength=0.0
        )

        # 计算效率（统一公式：Target Efficiency = EGFP / (EGFP + overlap) × 100%）
        denom = count_egfp + count_overlap
        if denom > 0:
            efficiency_value = (count_egfp / denom) * 100.0
            efficiency_text = f"{labels['efficiency_label']}: {efficiency_value:.1f}%"
        else:
            efficiency_text = labels['efficiency_na']

        # 底部第二行仅文字的效率图例（不含图例点）
        legend_eff = fig.legend(
            [mpl.lines.Line2D([], [], linestyle='')], [efficiency_text],
            loc='lower center',
            bbox_to_anchor=(0.5, 0.0),
            ncol=1,
            fontsize=36,
            frameon=False, fancybox=False, shadow=False, framealpha=0.90,
            columnspacing=0.8,
            handletextpad=0.2,
            handlelength=0.0
        )

        # 统一图例文字颜色
        for leg in [legend_counts, legend_eff]:
            if leg is not None:
                for t in leg.get_texts():
                    t.set_color(text_color)

        # ===== 为图例与标题动态预留空间，避免遮挡且不产生过多空白，与 Cell_Distribution_Scatter 一致 =====
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        # 图例高度（英寸）
        legend_eff_bbox_in = legend_eff.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
        legend_eff_h_in = legend_eff_bbox_in.height
        legend_counts_h_in = 0.0
        if legend_counts is not None:
            legend_counts_bbox_in = legend_counts.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
            legend_counts_h_in = legend_counts_bbox_in.height
        # 两行图例之间的视觉间距
        legend_vgap_in = 0.06
        legend_total_h_in = legend_eff_h_in + legend_counts_h_in + legend_vgap_in

        # 额外测量 X 轴刻度与标签高度（我们已移除，作为兜底保留0）
        xtick_h_in = 0.0
        xlabel_h_in = 0.0

        fig_w_in, fig_h_in = fig.get_size_inches()
        padding_bottom_in = 0.12
        bottom_margin = (legend_total_h_in + xtick_h_in + xlabel_h_in + padding_bottom_in) / fig_h_in
        bottom_margin = max(bottom_margin, 0.12)
        bottom_margin = min(bottom_margin, 0.50)

        # 顶部留白：根据标题高度动态计算
        title_h_in = 0.0
        try:
            title_obj = ax.title
            if title_obj and title_obj.get_text():
                t_bb_in = title_obj.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
                title_h_in = t_bb_in.height
        except Exception:
            title_h_in = 0.0
        padding_top_in = 0.06
        top_margin = (title_h_in + padding_top_in) / fig_h_in
        top_frac = 1.0 - max(min(top_margin, 0.15), 0.02)

        # 左右边距：保持左右对称，避免裁切
        ytick_w_in = 0.0
        ylabel_w_in = 0.0
        padding_left_in = 0.06
        left_margin = (ytick_w_in + ylabel_w_in + padding_left_in) / fig_w_in
        left_margin = max(left_margin, 0.05)
        left_margin = min(left_margin, 0.30)
        right_frac = 1.0 - left_margin

        fig.subplots_adjust(left=left_margin, right=right_frac, top=top_frac, bottom=bottom_margin)

        # ===== 标题：完全采用 Cell_Distribution_Scatter.py 的方法 =====
        # 从输入 CSV 的父目录名解析靶点（如 Cas9-site11），格式示例：0606_293T_cas9-sg11_1
        title_text = None
        try:
            base_name = os.path.basename(os.path.dirname(input_csv))
            parts = base_name.split('_')
            target_part = parts[2] if len(parts) >= 3 else base_name
            m = re.search(r"(?i)(cas\d+)-sg(\d+)", target_part)
            if m:
                cas_digits = re.search(r"(\d+)", m.group(1)).group(1)
                site_digits = m.group(2)
                title_text = f"Cas{cas_digits}-site{site_digits}"
        except Exception:
            title_text = None

        # 移除标题显示（按用户要求不再设置图标题）
        # 保留上方留白的自适应逻辑，但不绘制标题文本

        fixed_dpi = 600  # 固定dpi
        # 移除 bbox_inches='tight' 以严格使用用户设置的 figsize
        plt.savefig(output_img_base + ".png", dpi=fixed_dpi)
        plt.savefig(output_img_base + ".pdf", dpi=fixed_dpi)
        plt.close()

        return True
    except Exception as e:
        print(f"Error processing {input_csv}: {e}")
        return False

def batch_process(input_root, output_root, colors, figsize, point_size, lang):
    total_processed = 0
    for root, _, files in os.walk(input_root):
        count = 0
        for file in files:
            if file.endswith('_combined.csv'):
                input_csv = os.path.join(root, file)
                if process_and_plot_csv(input_csv, input_root, output_root, colors, figsize, point_size, lang):
                    count += 1
        if count > 0:
            print(f"处理目录: {root}")
            print(f"生成图表: {count} 张")
            total_processed += count
    return total_processed

def main():
    parser = argparse.ArgumentParser(description="批量处理 CSV 文件并生成图像")
    parser.add_argument('--input', required=True, help="输入根目录路径")
    parser.add_argument('--output', required=True, help="输出根目录路径")
    parser.add_argument('--colors', nargs=3, default=['#238C2A', '#8B0000', '#F2B90C'],
                        help="颜色值（顺序：EGFP、mcherry、Overlap）")
    parser.add_argument('--figsize', nargs=2, type=float, default=[8, 8], help="图像尺寸")
    parser.add_argument('--point_size', type=int, default=35, help="点的大小")
    parser.add_argument("--lang", type=str, default="en", choices=["zh", "en"], help="Language for labels (zh or en)")

    args = parser.parse_args()

    colors = {
        'EGFP': args.colors[0],
        'mcherry': args.colors[1],
        'Overlap': args.colors[2],
        'EGFP+mcherry': args.colors[2],  # 兼容旧标签，颜色与 Overlap 保持一致
    }

    total_processed = batch_process(
        args.input, args.output, colors, tuple(args.figsize), args.point_size, args.lang
    )

    print(f"\n处理完成！共生成 {total_processed} 张分析图表")
    print(f"输出目录: {os.path.abspath(args.output)}")

if __name__ == "__main__":
    main()

