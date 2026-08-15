"""Generate grouped box plot with i18n support."""

# -*- coding: utf-8 -*-
import argparse
import io
import os
import re
import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import is_color_like


if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

mpl.rcParams["font.family"] = "DejaVu Sans"
mpl.rcParams["axes.unicode_minus"] = False

TEXT_COLOR = "black"
mpl.rcParams["text.color"] = TEXT_COLOR
mpl.rcParams["axes.labelcolor"] = TEXT_COLOR
mpl.rcParams["axes.titlecolor"] = TEXT_COLOR
mpl.rcParams["xtick.color"] = TEXT_COLOR
mpl.rcParams["ytick.color"] = TEXT_COLOR

CHART_CONFIG = {
    "font": {
        "label": 40,
        "axis": 40,
        "mean_label": 36,
    },
    "box": {
        "width": 0.25,
        "group_spacing": 0.6,
    },
    "y_axis": {
        "min_value": 5,
        "padding": 1.5,  # 增加到1.5，为右上角标签留出更多空间
    },
}

LABELS_EN = {
    "y_axis": "Target Efficiency (%)",
    "mean_prefix": "Mean",
    "overall_mean": "Overall Mean",
}

LABELS = {
    "en": LABELS_EN,
    "zh": LABELS_EN.copy(),
}


def validate_colors(color_list):
    return [color for color in color_list if is_color_like(color)]


def extract_cas_sg_format(sample_name):
    """
    提取并格式化靶点标签，用于图表显示
    cas9 -> SpCas9, cas12 -> hfCas12Max
    sg1 -> site1, sg2 -> site2, ...
    """
    match = re.search(r"(cas\d+)-sg(\d+)", sample_name, re.IGNORECASE)
    if match:
        cas_type = match.group(1).lower()
        sg_number = match.group(2)
        
        # 将内部名称转换为显示名称
        if cas_type == "cas9":
            display_cas = "SpCas9"
        elif cas_type == "cas12":
            display_cas = "hfCas12Max"
        else:
            display_cas = cas_type.upper()  # 其他类型保持大写
        
        # sg → site 转换
        return f"{display_cas}-site{sg_number}"
    return sample_name


def extract_cas_type(sample_name):
    match = re.search(r"(cas\d+)", sample_name, re.IGNORECASE)
    return match.group(1).lower() if match else None


def has_multiple_cas_types(df):
    """检查数据中是否有多个不同的蛋白类型（Cas类型）"""
    cas_types = {extract_cas_type(sample) for sample in df["sample"] if extract_cas_type(sample)}
    return len(cas_types) > 1  # 改为 > 1，只有真正多个蛋白时才返回True


def extract_cas_order(target_name):
    """提取Cas类型用于排序，Cas9=1, Cas12=2, 其他=99"""
    match = re.search(r"cas(\d+)", target_name, re.IGNORECASE)
    if match:
        cas_num = int(match.group(1))
        if cas_num == 9:
            return 1  # Cas9排在最前
        elif cas_num == 12:
            return 2  # Cas12排在第二
        else:
            return 50 + cas_num  # 其他Cas类型
    return 99  # 没有匹配到Cas类型


def process_data(input_dir):
    input_path = os.path.join(input_dir, "all_summary.csv")
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Cannot find all_summary.csv in {input_dir}")

    df = pd.read_csv(input_path)
    if "sample" not in df.columns or "Target_Efficiency (%)" not in df.columns:
        raise ValueError("CSV must contain 'sample' and 'Target_Efficiency (%)' columns")

    df = df.rename(columns={"Target_Efficiency (%)": "TargetEfficiency"})
    
    # 支持两种格式：
    # 格式1: 0606_293T_cas9-sg3-10 (没有重复编号，只有视野)
    # 格式2: 0606_293T_cas9-sg3_1-10 (有重复编号_1，视野-10)
    # 正则: (.+?)_(\d+)-\d+$ 匹配格式2，(.+?)-(\d+)$ 匹配格式1
    # 优先尝试格式2（包含 _数字-数字 的模式）
    extracted = df["sample"].str.extract(r"(.+?)_(\d+)-\d+$", expand=True)
    
    # 如果格式2匹配失败，尝试格式1（只有 -数字 结尾）
    mask_null = extracted[0].isnull()
    if mask_null.any():
        extracted_alt = df.loc[mask_null, "sample"].str.extract(r"(.+?)-(\d+)$", expand=True)
        extracted.loc[mask_null, 0] = extracted_alt[0]
        extracted.loc[mask_null, 1] = extracted_alt[1]
    
    if extracted.isnull().any().any():
        raise ValueError("Failed to extract 'Main_Target' and 'Replicate' from sample column")

    df["Main_Target"] = extracted[0].str.lower()
    df["Replicate"] = extracted[1].astype(int)
    df["Display_Label"] = df["sample"].apply(extract_cas_sg_format)

    def extract_sg_number(target_name):
        match = re.search(r"sg(\d+)", target_name, re.IGNORECASE)
        return int(match.group(1)) if match else 9999

    unique_targets = pd.unique(df["Main_Target"])
    temp_df = pd.DataFrame(
        {
            "Target": unique_targets,
            "Cas_Order": [extract_cas_order(t) for t in unique_targets],
            "SG_Number": [extract_sg_number(t) for t in unique_targets],
        }
    )
    # 先按Cas类型排序（Cas9在前），再按sg编号排序
    temp_df = temp_df.sort_values(by=["Cas_Order", "SG_Number", "Target"])
    main_targets_sorted = temp_df["Target"].tolist()
    df["Main_Target"] = pd.Categorical(df["Main_Target"], categories=main_targets_sorted, ordered=True)

    return df, main_targets_sorted


def prepare_colors(args, n_groups):
    if args.colors:
        valid_colors = validate_colors(args.colors)
        if not valid_colors:
            return sns.color_palette(args.palette, n_groups).as_hex()
        num_colors = len(valid_colors)
        return [valid_colors[i % num_colors] for i in range(n_groups)]
    return sns.color_palette(args.palette, n_groups).as_hex()


def calculate_adaptive_box_width(n_boxes, figsize_width=12):
    """
    根据箱体数量自适应计算箱宽和间距
    - 少量箱体：箱体较窄，间距较大
    - 4个以上：箱体明显宽于间距
    """
    if n_boxes <= 3:
        # 1-3个箱体：窄箱体，大间距
        box_width = 0.4
        group_spacing = 1.0
    elif n_boxes <= 6:
        # 4-6个箱体：箱体宽度是间距的3倍
        box_width = 0.75
        group_spacing = 0.25
    elif n_boxes <= 12:
        # 7-12个箱体：箱体宽度是间距的4倍
        box_width = 0.8
        group_spacing = 0.2
    else:
        # 12个以上箱体：箱体宽度是间距的5倍以上
        total_space = figsize_width * 0.95
        box_width = total_space / (n_boxes * 1.2)
        group_spacing = box_width * 0.15  # 间距仅为箱宽的15%
    
    return box_width, group_spacing


def generate_positions(main_targets_sorted, replicates, df, figsize_width=12):
    """
    生成X轴位置
    - 多蛋白模式：每个靶点（Main_Target）一个箱体
    - 单蛋白模式：每个靶点的每个重复一个箱体
    """
    x_positions = {}
    x_ticks = []
    current_x = 0
    
    # 判断是否为多蛋白模式
    is_multi_protein = has_multiple_cas_types(df)
    
    # 计算箱体总数
    if is_multi_protein:
        n_boxes = len(main_targets_sorted)
    else:
        n_boxes = len(main_targets_sorted) * len(replicates)
    
    # 自适应计算箱宽和间距
    box_width, group_spacing = calculate_adaptive_box_width(n_boxes, figsize_width)
    
    if is_multi_protein:
        # 多蛋白模式：每个靶点一个箱体
        for target in main_targets_sorted:
            x_positions[target] = current_x
            x_ticks.append(current_x)
            current_x += box_width + group_spacing
    else:
        # 单蛋白模式：按靶点分组，展示每个重复
        for target in main_targets_sorted:
            group_start = current_x
            for rep in replicates:
                x_positions[(target, rep)] = current_x
                current_x += box_width
            group_center = group_start + (box_width * len(replicates)) / 2 - box_width / 2
            x_ticks.append(group_center)
            current_x += group_spacing
    
    return x_positions, x_ticks, current_x, is_multi_protein, box_width


def plot_boxplot(df, main_targets_sorted, args, output_dir, lang="zh"):
    labels = LABELS.get(lang, LABELS["zh"])
    replicates = sorted(df["Replicate"].unique())
    palette = prepare_colors(args, len(main_targets_sorted))

    x_positions, x_ticks, _, is_multi_protein, box_width = generate_positions(
        main_targets_sorted, replicates, df, figsize_width=args.figsize[0]
    )

    plt.figure(figsize=tuple(args.figsize))
    ax = plt.gca()

    box_data = []
    box_positions = []
    box_colors = []

    if is_multi_protein:
        # 多蛋白模式：每个靶点一个箱体（合并所有重复数据）
        for target in main_targets_sorted:
            subset = df[df["Main_Target"] == target]["TargetEfficiency"].dropna()
            box_data.append(subset)
            box_positions.append(x_positions[target])
            box_colors.append(palette[main_targets_sorted.index(target)])
    else:
        # 单蛋白模式：每个靶点的每个重复一个箱体
        for target in main_targets_sorted:
            for rep in replicates:
                subset = df[(df["Main_Target"] == target) & (df["Replicate"] == rep)]["TargetEfficiency"].dropna()
                box_data.append(subset)
                box_positions.append(x_positions[(target, rep)])
                box_colors.append(palette[main_targets_sorted.index(target)])

    box = ax.boxplot(
        box_data,
        positions=box_positions,
        widths=box_width * 0.9,
        patch_artist=True,
        showfliers=False,
        medianprops=dict(color="black", linewidth=1.5),
    )
    for patch, color in zip(box["boxes"], box_colors):
        patch.set_facecolor(color)
        patch.set_alpha(1.0)

    # 绘制散点
    if is_multi_protein:
        # 多蛋白模式：所有数据点显示在对应靶点的箱体上
        for target in main_targets_sorted:
            y = df[df["Main_Target"] == target]["TargetEfficiency"]
            x_center = x_positions[target]
            x_jitter = np.random.uniform(
                -box_width * 0.25,
                box_width * 0.25,
                size=len(y),
            )
            ax.scatter(
                x_center + x_jitter,
                y,
                color="black",
                edgecolor="black",
                s=30,
                alpha=0.6,
                zorder=3,
            )
    else:
        # 单蛋白模式：按重复分别显示数据点
        for target in main_targets_sorted:
            for rep in replicates:
                y = df[(df["Main_Target"] == target) & (df["Replicate"] == rep)]["TargetEfficiency"]
                x_center = x_positions[(target, rep)]
                x_jitter = np.random.uniform(
                    -box_width * 0.25,
                    box_width * 0.25,
                    size=len(y),
                )
                ax.scatter(
                    x_center + x_jitter,
                    y,
                    color="black",
                    edgecolor="black",
                    s=30,
                    alpha=0.6,
                    zorder=3,
                )

    display_labels = [df[df["Main_Target"] == target]["Display_Label"].iloc[0] for target in main_targets_sorted]

    # 移除x轴标签，使用图例替代
    ax.set_xticks([])
    ax.set_ylabel(labels["y_axis"], fontsize=CHART_CONFIG["font"]["label"])
    ax.tick_params(axis="y", labelsize=CHART_CONFIG["font"]["axis"])
    
    # 添加图例
    if is_multi_protein:
        # 多蛋白模式：创建图例条目
        # 按蛋白类型分组，让同一sg编号的Cas9和Cas12在同一行
        cas9_targets = []
        cas12_targets = []
        other_targets = []
        
        for target in main_targets_sorted:
            cas_type = extract_cas_type(df[df["Main_Target"] == target]["sample"].iloc[0])
            if cas_type and 'cas9' in cas_type.lower():
                cas9_targets.append(target)
            elif cas_type and 'cas12' in cas_type.lower():
                cas12_targets.append(target)
            else:
                other_targets.append(target)
        
        # 按列排列：先填充左列（所有Cas9），再填充右列（所有Cas12）
        # matplotlib的ncol=2是按行填充，所以需要交错排列
        # 例如：[cas9-sg1, cas9-sg2, cas12-sg1, cas12-sg2] -> 显示为：
        #   cas9-sg1  cas12-sg1
        #   cas9-sg2  cas12-sg2
        max_len = max(len(cas9_targets), len(cas12_targets))
        legend_handles = []
        legend_labels = []
        
        # 先添加所有Cas9
        for target in cas9_targets:
            color_idx = main_targets_sorted.index(target)
            display_label = df[df["Main_Target"] == target]["Display_Label"].iloc[0]
            handle = mpl.patches.Patch(facecolor=palette[color_idx], edgecolor='black', linewidth=0.5)
            legend_handles.append(handle)
            legend_labels.append(display_label)
        
        # 再添加所有Cas12
        for target in cas12_targets:
            color_idx = main_targets_sorted.index(target)
            display_label = df[df["Main_Target"] == target]["Display_Label"].iloc[0]
            handle = mpl.patches.Patch(facecolor=palette[color_idx], edgecolor='black', linewidth=0.5)
            legend_handles.append(handle)
            legend_labels.append(display_label)
        
        # 添加其他类型
        for target in other_targets:
            color_idx = main_targets_sorted.index(target)
            display_label = df[df["Main_Target"] == target]["Display_Label"].iloc[0]
            handle = mpl.patches.Patch(facecolor=palette[color_idx], edgecolor='black', linewidth=0.5)
            legend_handles.append(handle)
            legend_labels.append(display_label)
        
        ax.legend(legend_handles, legend_labels, 
                 loc='upper left', 
                 fontsize=28,
                 frameon=False,
                 handletextpad=0.5,
                 columnspacing=1.5,
                 labelspacing=0.5,
                 ncol=2)
    else:
        # 单蛋白模式：创建图例条目（每个靶点一个颜色）
        legend_handles = []
        legend_labels = []
        for target in main_targets_sorted:
            color_idx = main_targets_sorted.index(target)
            display_label = df[df["Main_Target"] == target]["Display_Label"].iloc[0]
            handle = mpl.patches.Patch(facecolor=palette[color_idx], edgecolor='black', linewidth=0.5)
            legend_handles.append(handle)
            legend_labels.append(display_label)
        
        ax.legend(legend_handles, legend_labels, 
                 loc='upper left', 
                 fontsize=28,
                 frameon=False,
                 handletextpad=0.5,
                 columnspacing=1.5,
                 labelspacing=0.5,
                 ncol=2,
                 bbox_to_anchor=(0, 1.0))

    # 设置y轴范围，为右上角的标签留出空间
    y_max = max(
        df["TargetEfficiency"].max() * CHART_CONFIG["y_axis"]["padding"],
        CHART_CONFIG["y_axis"]["min_value"],
    )
    ax.set_ylim(0, y_max)

    ax.spines["right"].set_visible(False)
    for spine in ax.spines.values():
        spine.set_color(TEXT_COLOR)

    # 调整布局，为顶部图例预留空间
    plt.subplots_adjust(top=0.85)

    output_path_png = os.path.join(output_dir, "boxplot_TargetEfficiency.png")
    # 移除 bbox_inches="tight" 以严格使用用户设置的 figsize
    plt.savefig(output_path_png, dpi=600)

    output_path_pdf = os.path.join(output_dir, "boxplot_TargetEfficiency.pdf")
    plt.savefig(output_path_pdf, dpi=600)

    plt.close()
    print(f"Box plot saved to:\n  {output_path_png}\n  {output_path_pdf}")


def main():
    parser = argparse.ArgumentParser(description="绘制Target Efficiency箱线图")
    parser.add_argument("--input", required=True, help="输入目录，包含 all_summary.csv")
    parser.add_argument("--output", help="输出目录，默认与输入目录相同")
    parser.add_argument("--figsize", nargs=2, type=float, default=[12, 6], help="图表尺寸(宽 高)")
    parser.add_argument("--colors", nargs="+", default=[], help="自定义颜色列表")
    parser.add_argument("--palette", default="Set2", help="Seaborn调色板名")
    parser.add_argument("--lang", default="zh", choices=["zh", "en"], help="图表语言 (zh/en)")
    args = parser.parse_args()

    try:
        output_dir = args.output if args.output else args.input
        os.makedirs(output_dir, exist_ok=True)
        df, main_targets_sorted = process_data(args.input)
        plot_boxplot(df, main_targets_sorted, args, output_dir, lang=args.lang)
        print("SUCCESS: Box plot generated successfully!")
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()

