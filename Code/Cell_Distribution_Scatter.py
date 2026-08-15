# -*- coding: utf-8 -*-
import numpy as np
import matplotlib.pyplot as plt
import os
import argparse
from collections import defaultdict
import re
from scipy.spatial import KDTree
from matplotlib.colors import is_color_like
import matplotlib as mpl
import csv
import sys
import io

# 确保在Windows环境下正确处理Unicode字符
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 设置字体类型（全局）
mpl.rcParams['font.family'] = 'DejaVu Sans'
mpl.rcParams['axes.unicode_minus'] = False

# 标签文本（图片内文字统一使用英文，避免 DejaVu Sans 无法渲染中文导致方框）
LABELS_ZH = {
    "title": "Cell Position Distribution",
    "egfp_label": "GFP",
    "mcherry_label": "mCherry",
    "overlap_label": "Overlap",
    "efficiency_label": "Target Efficiency"
}

LABELS_EN = {
    "title": "Cell Position Distribution",
    "egfp_label": "GFP",
    "mcherry_label": "mCherry",
    "overlap_label": "Overlap",
    "efficiency_label": "Target Efficiency"
}

# 合并语言字典
LABELS = {
    "zh": LABELS_ZH,
    "en": LABELS_EN
}

class CellPositionAnalyzer:
    def __init__(self):
        self.args = self.parse_arguments()
        self.lang = self.args.lang
        self.labels = LABELS.get(self.lang, LABELS["en"])
        self.validate_arguments()
        self.colors = {
            "egfp": self.args.colors[0],
            "mcherry": self.args.colors[1],
            "overlap": self.args.colors[2]
        }
        # >>>>>> 统一字体颜色可调  <<<<<<
        self.text_color = 'black'      # 只改这里即可换色
        # 图例中代表性的三个点（EGFP、mCherry、Overlap）的大小（单位：points）。按需调整即可生效。
        self.legend_marker_sizes = {
            "egfp": 19,
            "mcherry": 19,
            "overlap": 19
        }
        # 全局统一字体颜色（无需命令行参数）：标题、轴标签、刻度、文本、图例文字
        mpl.rcParams['text.color'] = self.text_color
        mpl.rcParams['axes.labelcolor'] = self.text_color
        mpl.rcParams['axes.titlecolor'] = self.text_color
        mpl.rcParams['xtick.color'] = self.text_color
        mpl.rcParams['ytick.color'] = self.text_color

        self.file_pattern = re.compile(
            r'^(?P<base>.+?)[_-](?P<channel>EGFP|mCherry)[_-](?P<sample_id>\d+)_cp_outlines\.txt$',
            re.IGNORECASE
        )
        self.dpi = 600
        self.summary = []

    def parse_arguments(self):
        parser = argparse.ArgumentParser(description="Dual-channel cell position analysis tool")
        parser.add_argument("-i", "--input", required=True, help="Input directory")
        parser.add_argument("-o", "--output", required=True, help="Output directory")
        parser.add_argument("-d", "--distance", type=int, default=15, help="Matching distance threshold")
        parser.add_argument("--figsize", nargs=2, type=int, default=[12, 12], metavar=("WIDTH", "HEIGHT"))
        parser.add_argument("--colors", nargs=3, default=["#238C2A", "#BF0B3B", "#F2B90C"],
                            metavar=("EGFP", "MCHERRY", "OVERLAP"))
        parser.add_argument("--point_size", type=int, default=35, help="Scatter point size")
        parser.add_argument("--lang", type=str, default="en", choices=["zh", "en"], help="Language for labels (zh or en)")
        return parser.parse_args()

    def validate_arguments(self):
        if not os.path.isdir(self.args.input):
            raise ValueError(f"Input directory does not exist: {self.args.input}")
        if self.args.distance < 1:
            raise ValueError("Distance threshold must be greater than 0")
        for color in self.args.colors:
            if not is_color_like(color):
                raise ValueError(f"Invalid color format: {color}")
        if self.args.point_size < 1:
            raise ValueError("Point size must be greater than 0")

    @staticmethod
    def extract_centers(filepath):
        centers = set()
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    coords = list(map(int, line.strip().split(',')))
                    if len(coords) % 2 == 0:
                        x = int(np.mean(coords[::2]))
                        y = int(np.mean(coords[1::2]))
                        centers.add((x, y))
        except Exception as e:
            print(f"Error reading file {filepath}: {str(e)}")
        return centers

    def compute_overlap(self, set_a, set_b):
        """一对一匹配：每个红色细胞最多匹配一个绿色细胞，避免重复使用。
        每个绿色点依次查询最近的、尚未被占用的红色点，距离<=阈值才算 overlap。"""
        if not set_b:
            return set(), set_a, set()
        b_list = list(set_b)
        tree = KDTree(b_list)
        matched = set()
        used_b = set()
        k = min(len(b_list), 10)
        for point in set_a:
            dists, idxs = tree.query(point, k=k)
            dists = np.atleast_1d(dists)
            idxs = np.atleast_1d(idxs)
            for dist, idx in zip(dists, idxs):
                if dist > self.args.distance:
                    break
                red_point = b_list[int(idx)]
                if red_point in used_b:
                    continue  # 该红色细胞已被占用，尝试下一个最近红色细胞
                matched.add(point)
                used_b.add(red_point)
                break
        return matched, set_a - matched, set_b - used_b

    def process_directory(self, current_dir):
        file_groups = defaultdict(dict)
        for filename in os.listdir(current_dir):
            match = self.file_pattern.match(filename)
            if match:
                groups = match.groupdict()
                key = f"{groups['base']}-{groups['sample_id']}"
                file_groups[key][groups['channel'].lower()] = os.path.join(current_dir, filename)

        processed = 0
        for key, files in file_groups.items():
            if 'egfp' not in files or 'mcherry' not in files:
                continue
            try:
                egfp = self.extract_centers(files['egfp'])
                mcherry = self.extract_centers(files['mcherry'])

                if not egfp and not mcherry:
                    continue

                overlap, only_egfp, only_mcherry = self.compute_overlap(egfp, mcherry)
                plt.figure(figsize=tuple(self.args.figsize))

                egfp_only_count = len(only_egfp)
                mcherry_only_count = len(only_mcherry)
                overlap_count = len(overlap)
                total_count = egfp_only_count + mcherry_only_count + overlap_count

                if only_egfp:
                    plt.scatter(*zip(*only_egfp), s=self.args.point_size, c=self.colors['egfp'], alpha=0.7,
                                label=f'{self.labels["egfp_label"]}: {egfp_only_count}')
                if only_mcherry:
                    plt.scatter(*zip(*only_mcherry), s=self.args.point_size, c=self.colors['mcherry'], alpha=0.7,
                                label=f'{self.labels["mcherry_label"]}: {mcherry_only_count}')
                if overlap:
                    plt.scatter(*zip(*overlap), s=self.args.point_size + 5, c=self.colors['overlap'],
                                label=f'{self.labels["overlap_label"]}: {overlap_count}')

                plt.gca().invert_yaxis()
                # 减少坐标轴内部的默认留白，使数据更贴近边界（保留少量美观留白）
                ax = plt.gca()
                # 尽量减少左右空白：去除 x 方向数据边距（保持 y 方向少量留白）
                ax.margins(x=0.0, y=0.02)
                # 去掉 X/Y 轴的标签与刻度，并清除遗留空白
                ax.set_xlabel('')
                ax.set_ylabel('')
                ax.set_xticks([])
                ax.set_yticks([])
                ax.tick_params(bottom=False, labelbottom=False, left=False, labelleft=False)
                
                # 获取图例信息
                handles, labels = plt.gca().get_legend_handles_labels()
                num_items = len(labels)

                # 计算并在标签中展示 Target Efficiency = EGFP/(EGFP+overlap)（百分比，保留 1 位小数）
                # 注：统一公式为 EGFP/(EGFP+overlap)，其中EGFP为仅EGFP细胞数
                try:
                    denom = egfp_only_count + overlap_count
                    if denom > 0:
                        efficiency_pct = (egfp_only_count / denom) * 100.0
                        efficiency_text = f'{self.labels["efficiency_label"]}: {efficiency_pct:.1f}%'
                    else:
                        efficiency_text = f'{self.labels["efficiency_label"]}: N/A'
                except Exception:
                    efficiency_text = f'{self.labels["efficiency_label"]}: N/A'

                # 确保“Target Efficiency”标签仅出现一次且排在最后
                # 先移除已有的效率标签（如果之前存在），再在末尾追加
                filtered = [
                    (h, l) for h, l in zip(handles, labels)
                    if not str(l).strip().startswith(self.labels["efficiency_label"])
                ]
                handles = [h for h, _ in filtered]
                labels = [l for _, l in filtered]

                # 使用代理 artist 在图例中加入纯文本条目，并置于末尾
                efficiency_handle = mpl.lines.Line2D([], [], linestyle='')
                handles.append(efficiency_handle)
                labels.append(efficiency_text)
                num_items = len(labels)

                # 从子目录名解析靶点并在散点图上方添加标题（如 Cas9-site11）
                # 目录名格式示例：0606_293T_cas9-sg11_1 或 0606_293T_Cas9-sg11_2
                title_text = None
                try:
                    base_name = os.path.basename(current_dir)
                    parts = base_name.split('_')
                    # 目录结构：<prefix>_<target>_<rep>，靶点部分在第 3 段（索引 2）
                    target_part = parts[2] if len(parts) >= 3 else base_name
                    m = re.search(r"(?i)(cas\d+)-sg(\d+)", target_part)
                    if m:
                        cas_digits = re.search(r"(\d+)", m.group(1)).group(1)
                        site_digits = m.group(2)
                        title_text = f"Cas{cas_digits}-site{site_digits}"
                except Exception:
                    title_text = None

                # 不再显示标题
                # if title_text:
                #     ax.set_title(title_text, fontsize=36, pad=24, color=self.text_color)

                # 使用两个图例：
                # 1) 数量标签一行（EGFP-only、mCherry-only、Overlap）
                # 2) 效率标签单独一行并居中（Target Efficiency）
                fig = plt.gcf()

                count_pairs = [
                    (h, l) for h, l in zip(handles, labels)
                    if not str(l).strip().startswith("Target Efficiency")
                ]
                count_handles = [h for h, _ in count_pairs]
                count_labels = [l for _, l in count_pairs]

                # 为数量图例构造代理句柄，以便自定义图例点大小（EGFP/mCherry/Overlap）
                count_handles_proxy = []
                for l in count_labels:
                    label_str = str(l).strip()
                    # 修复：使用 'GFP' 而不是 'EGFP' 来匹配标签
                    if label_str.startswith('GFP'):
                        ms = getattr(self, 'legend_marker_sizes', {}).get('egfp', 19)
                        color = self.colors['egfp']
                    elif label_str.startswith('mCherry'):
                        ms = getattr(self, 'legend_marker_sizes', {}).get('mcherry', 19)
                        color = self.colors['mcherry']
                    elif label_str.startswith('Overlap'):
                        ms = getattr(self, 'legend_marker_sizes', {}).get('overlap', 19)
                        color = self.colors['overlap']
                    else:
                        ms = 19
                        color = '#666666'
                    proxy = mpl.lines.Line2D([], [], linestyle='', marker='o',
                                             markersize=ms,
                                             markerfacecolor=color,
                                             markeredgecolor=color)
                    count_handles_proxy.append(proxy)

                # 数量图例（单行，底部居中，稍稍上移，为效率留一行空间）
                legend_counts = None
                if len(count_labels) > 0:
                    legend_counts = fig.legend(count_handles_proxy, count_labels,
                                               loc='lower center',
                                               bbox_to_anchor=(0.5, 0.08),
                                               ncol=len(count_labels),
                                               fontsize=36,
                                               frameon=False, fancybox=False, shadow=False,
                                               columnspacing=1.2,
                                               handletextpad=0.3,
                                               handlelength=0.0)

                # 效率图例（单独一行，底部居中）
                legend_eff = fig.legend([efficiency_handle], [efficiency_text],
                                        loc='lower center',
                                        bbox_to_anchor=(0.5, 0.0),
                                        ncol=1,
                                        fontsize=36,
                                        frameon=False, fancybox=False, shadow=False, framealpha=0.90,
                                        columnspacing=0.8,
                                        handletextpad=0.2,
                                        handlelength=0.0)

                # 统一图例文字颜色
                for leg in [legend_counts, legend_eff]:
                    if leg is not None:
                        for t in leg.get_texts():
                            t.set_color(self.text_color)

                # 计算两个图例的总高度，动态为图例预留空间，使散点图与图例不遮挡
                fig.canvas.draw()
                renderer = fig.canvas.get_renderer()
                legend_eff_bbox_in = legend_eff.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
                legend_eff_h_in = legend_eff_bbox_in.height
                legend_counts_h_in = 0.0
                if legend_counts is not None:
                    legend_counts_bbox_in = legend_counts.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
                    legend_counts_h_in = legend_counts_bbox_in.height
                # 两行图例之间的视觉间距（英寸），避免边框或内容看起来拥挤
                legend_vgap_in = 0.06
                legend_total_h_in = legend_eff_h_in + legend_counts_h_in + legend_vgap_in

                # 额外测量 X 轴刻度与标签高度，确保也能避让它们
                xtick_h_in = 0.0
                for tick in ax.get_xticklabels():
                    if tick.get_visible():
                        bb_in = tick.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
                        xtick_h_in = max(xtick_h_in, bb_in.height)

                xlabel_h_in = 0.0
                xlabel_text = ax.get_xlabel()
                if xlabel_text:
                    xl_bb_in = ax.xaxis.label.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
                    xlabel_h_in = xl_bb_in.height

                fig_w_in, fig_h_in = fig.get_size_inches()
                padding_bottom_in = 0.12  # 适度底部缓冲，避免产生过多空白
                bottom_margin = (legend_total_h_in + xtick_h_in + xlabel_h_in + padding_bottom_in) / fig_h_in

                # 兜底：适度范围，既不遮挡也不过度留白
                bottom_margin = max(bottom_margin, 0.12)
                bottom_margin = min(bottom_margin, 0.50)

                # 顶部边距动态计算，考虑标题高度，保证不同图像大小下不遮挡
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
                # 上边距的合理范围，避免过度留白
                top_frac = 1.0 - max(min(top_margin, 0.15), 0.02)

                # 动态计算左侧边距，确保 Y 轴刻度与标签不被裁切
                ytick_w_in = 0.0
                for tick in ax.get_yticklabels():
                    if tick.get_visible():
                        bb_in = tick.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
                        ytick_w_in = max(ytick_w_in, bb_in.width)

                ylabel_w_in = 0.0
                ylabel_text = ax.get_ylabel()
                if ylabel_text:
                    yl_bb_in = ax.yaxis.label.get_window_extent(renderer).transformed(fig.dpi_scale_trans.inverted())
                    ylabel_w_in = yl_bb_in.width

                # 去除刻度与标签后减少左侧缓冲
                padding_left_in = 0.06
                left_margin = (ytick_w_in + ylabel_w_in + padding_left_in) / fig_w_in
                left_margin = max(left_margin, 0.05)
                left_margin = min(left_margin, 0.30)

                # 左右对称边距：与左侧留白比例一致，减少无用空白且左右对称
                right_frac = 1.0 - left_margin

                # 调整子图边距：尽量填满整图，同时为图例与轴元素预留空间
                fig.subplots_adjust(left=left_margin, right=right_frac, top=top_frac, bottom=bottom_margin)
                plt.grid(False)

                # >>>>>>  统一改字体颜色  <<<<<<
                plt.gca().tick_params(colors=self.text_color)
                for spine in plt.gca().spines.values():
                    spine.set_color(self.text_color)
                # 统一轴标签颜色
                try:
                    ax.xaxis.label.set_color(self.text_color)
                    ax.yaxis.label.set_color(self.text_color)
                except Exception:
                    pass
                # 如果以后加标题：plt.title(..., color=self.text_color)

                # 使用 subplots_adjust 已为图例预留空间，这里不再调用 tight_layout 以免产生冲突

                rel_path = os.path.relpath(current_dir, self.args.input)
                output_dir = os.path.join(self.args.output, rel_path)
                os.makedirs(output_dir, exist_ok=True)

                output_file_base = os.path.join(output_dir, f"{key}_analysis")
                # 移除 bbox_inches='tight' 以严格使用用户设置的 figsize
                plt.savefig(output_file_base + ".png", dpi=self.dpi)
                plt.savefig(output_file_base + ".pdf", dpi=self.dpi)
                plt.close()

                self.summary.append({
                    "sample": key,
                    "EGFP_only": egfp_only_count,
                    "mcherry_only": mcherry_only_count,
                    "overlap": overlap_count,
                    "total": total_count
                })

                processed += 1
            except Exception as e:
                print(f"Error processing {key}: {str(e)}")
        return processed

    def write_summary_csv(self):
        output_file = os.path.join(self.args.output, "all_summary.csv")
        os.makedirs(self.args.output, exist_ok=True)
        with open(output_file, 'w', newline='') as f:
            fieldnames = ["sample", "EGFP_only", "mcherry_only", "overlap", "total", "Target_Efficiency (%)"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in self.summary:
                egfp_only = row["EGFP_only"]
                overlap = row["overlap"]
                # Target Efficiency = EGFP/(EGFP+overlap)（百分比，保留一位小数）
                denom = egfp_only + overlap
                if denom > 0:
                    ratio = (egfp_only / denom) * 100.0
                    row["Target_Efficiency (%)"] = f"{ratio:.1f}"
                else:
                    row["Target_Efficiency (%)"] = "N/A"
                writer.writerow(row)

    def run(self):
        total = 0
        for root, dirs, files in os.walk(self.args.input):
            if any(f.endswith('_cp_outlines.txt') for f in files):
                print(f"\nProcessing directory: {root}")
                count = self.process_directory(root)
                total += count
                print(f"Generated plots: {count}")
        self.write_summary_csv()
        print(f"\nProcessing completed! Total plots generated: {total}")
        print(f"Output directory: {os.path.abspath(self.args.output)}")


if __name__ == "__main__":
    try:
        analyzer = CellPositionAnalyzer()
        analyzer.run()
    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)
