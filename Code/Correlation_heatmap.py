#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
独立的CSV相关性热图生成脚本（简化参数版）

功能：
- 加载CSV数据（自动尝试多种编码）
- 自动检测数值列（跳过索引列）
- 计算Spearman或Pearson相关性（在代码顶部配置）
- 生成与原始PDF风格一致的相关性热图
- 标签中的百分号/括号移除（在代码顶部配置）
- 标签方向、字体大小与字体格式可在代码顶部直接修改（不通过命令行参数）

保留的命令行参数：
- 输入文件：csv_file（必选）
- 输出前缀：--output-prefix（可选）
- 图片大小：--figsize（可选，格式"宽,高"，默认6.02,5.20）

用法示例：
python csv_correlation_heatmap.py cas9.csv --output-prefix cas9_heatmap --figsize 6.02,5.20
"""

import os
from pathlib import Path
import argparse
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from scipy.stats import spearmanr, pearsonr
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



########################################
# 可在此处直接调整绘图配置（不通过命令行）
########################################
# 相关性方法：'spearman' 或 'pearson'
METHOD = 'spearman'

# 是否保留原始列名（若为False，将移除'(%)'、'%'、括号）
KEEP_LABELS = False

# 标签方向
X_ROT = 0      # x轴标签角度（0为横向）
Y_ROT = 90     # y轴标签角度（90为竖向）

# 字体族与分项字号（分开控制）
FONT_FAMILY = 'DejaVu Sans'   # 全局字体族，可改为 'Arial' 等
BASE_FONT_SIZE = 40           # 全局基础字号（用于未显式指定的元素）
X_TICK_FONT_SIZE = 40         # x轴刻度标签字号
Y_TICK_FONT_SIZE = 40         # y轴刻度标签字号
ANNOT_FONT_SIZE = 40          # 热图格子中文字（相关系数）字号
CBAR_TICK_FONT_SIZE = 30      # 颜色条刻度字号

# 颜色条尺寸与布局控制（避免颜色条高度超过热图高度）
# 可选方向: 'vertical'（竖向，默认）或 'horizontal'（横向，推荐用于严格控制高度）
CBAR_ORIENTATION = 'vertical'
# 当为 vertical 时，shrink < 1 可让颜色条长度小于热图高度
CBAR_SHRINK = 0.75
# 颜色条相对轴的厚度比例：vertical 为宽度占比；horizontal 为高度占比
CBAR_FRACTION = 0.05
# 颜色条与主图之间的间距
CBAR_PAD = 0.02

# 图像尺寸默认值（仍可通过命令行 --figsize 覆盖）
DEFAULT_FIGSIZE = (12, 12)


def setup_matplotlib():
    """设置matplotlib参数以匹配原始PDF样式"""
    plt.rcParams.update({
        'font.size': BASE_FONT_SIZE,
        'font.family': FONT_FAMILY,
        'axes.linewidth': 0.8,
        'xtick.major.width': 0.8,
        'ytick.major.width': 0.8,
        'xtick.minor.width': 0.4,
        'ytick.minor.width': 0.4,
        'figure.dpi': 600,
        'savefig.dpi': 600,
        'savefig.bbox': 'tight',
        'savefig.pad_inches': 0.1,
    })


def load_csv(csv_file: str) -> pd.DataFrame:
    """加载CSV数据，自动尝试不同编码。"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
    last_err = None
    for enc in encodings:
        try:
            df = pd.read_csv(csv_file, encoding=enc)
            print(f"成功加载数据，使用编码: {enc}")
            print(f"数据形状: {df.shape}")
            print("列名:", df.columns.tolist())
            print("\n数据预览:")
            print(df.head())
            return df
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"无法读取CSV文件，请检查文件编码。最后错误: {last_err}")


def get_numeric_columns(df: pd.DataFrame):
    """获取数值列，跳过明显的索引列。"""
    numeric_cols = []
    for col in df.columns:
        if 'unnamed' in col.lower() or col.lower() in ['index', 'id']:
            continue
        try:
            if df[col].dtype == 'object':
                test_series = (df[col].astype(str)
                                .str.replace('%', '')
                                .str.replace(',', '')
                                .str.strip())
                pd.to_numeric(test_series, errors='raise')
            else:
                pd.to_numeric(df[col], errors='raise')
            numeric_cols.append(col)
        except Exception:
            continue
    print(f"检测到数值列: {numeric_cols}")
    return numeric_cols


def clean_numeric_data(df: pd.DataFrame, columns):
    """清理数值数据，去除百分号、逗号等并转为数值。"""
    cleaned_df = df.copy()
    for col in columns:
        if cleaned_df[col].dtype == 'object':
            cleaned_df[col] = (cleaned_df[col].astype(str)
                               .str.replace('%', '')
                               .str.replace(',', '')
                               .str.replace('$', '')
                               .str.strip())
            cleaned_df[col] = pd.to_numeric(cleaned_df[col], errors='coerce')
    cleaned_df = cleaned_df.dropna(subset=columns)
    print(f"清理后数据形状: {cleaned_df.shape}")
    return cleaned_df[columns]


def print_correlation_details(data: pd.DataFrame, columns, method: str):
    print(f"\n详细{method.capitalize()}相关性分析:")
    for i in range(len(columns)):
        for j in range(i + 1, len(columns)):
            var1, var2 = columns[i], columns[j]
            if method.lower() == 'spearman':
                corr_coef, p_value = spearmanr(data[var1], data[var2])
                symbol = 'ρ'
            else:
                corr_coef, p_value = pearsonr(data[var1], data[var2])
                symbol = 'r'
            significance = "***" if p_value < 0.001 else "**" if p_value < 0.01 else "*" if p_value < 0.05 else ""
            print(f"{var1} vs {var2}: {symbol} = {corr_coef:.3f}, p = {p_value:.3f} {significance}")


def correlation_heatmap(df: pd.DataFrame,
                        columns,
                        method: str,
                        output_prefix='correlation_heatmap',
                        keep_labels: bool = False,
                        x_rot: int = 0,
                        y_rot: int = 90,
                        figsize=(6.02, 5.20),
                        show: bool = False):
    """创建并保存相关性热图。"""
    data = clean_numeric_data(df, columns)

    # 计算相关矩阵
    if method.lower() == 'spearman':
        corr_matrix = data.corr(method='spearman')
    else:
        corr_matrix = data.corr(method='pearson')
    print(f"\n{method.capitalize()}相关系数矩阵:")
    print(corr_matrix.round(3))

    # 处理标签
    if keep_labels:
        labels = columns
    else:
        labels = [c.replace('(%)', '').replace('%', '').replace('(', '').replace(')', '') for c in columns]
    corr_matrix.index = labels
    corr_matrix.columns = labels

    # 画图
    fig, ax = plt.subplots(figsize=figsize)
    heatmap = sns.heatmap(
        corr_matrix,
        annot=True,
        fmt='.3f',
        cmap='RdYlBu_r',
        center=0,
        square=True,
        cbar_kws={
            'orientation': CBAR_ORIENTATION,
            'shrink': CBAR_SHRINK,
            'fraction': CBAR_FRACTION,
            'pad': CBAR_PAD,
            'aspect': 20,
        },
        annot_kws={'size': ANNOT_FONT_SIZE, 'weight': 'normal', 'family': FONT_FAMILY},
        linewidths=0.5,
        linecolor='white',
        ax=ax
    )

    ax.set_xlabel('')
    ax.set_ylabel('')
    ax.set_xticklabels(ax.get_xticklabels(), rotation=x_rot, ha='center', fontsize=X_TICK_FONT_SIZE)
    ax.set_yticklabels(ax.get_yticklabels(), rotation=y_rot, va='center', fontsize=Y_TICK_FONT_SIZE)
    ax.tick_params(axis='x', pad=2)
    ax.tick_params(axis='y', pad=2)
    plt.tight_layout(pad=0.5)

    # 设置颜色条刻度字号
    try:
        cbar = ax.collections[0].colorbar if ax.collections else None
        if cbar is not None:
            cbar.ax.tick_params(labelsize=CBAR_TICK_FONT_SIZE)
    except Exception:
        pass

    out_path = Path(f"{output_prefix}_{method}.pdf")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(str(out_path), format='pdf', bbox_inches='tight', pad_inches=0.05, dpi=600)
    print(f"\n热图已保存为: {out_path}")

    print_correlation_details(data, columns, method)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return str(out_path)


def parse_figsize(s: str):
    try:
        parts = [p.strip() for p in s.split(',')]
        return (float(parts[0]), float(parts[1]))
    except Exception:
        raise argparse.ArgumentTypeError('figsize格式应为 "宽,高"，例如 "6.02,5.20"')


def main():
    parser = argparse.ArgumentParser(description='CSV相关性热图生成器（独立脚本，简化参数版）')
    parser.add_argument('csv_file', help='CSV文件路径')
    parser.add_argument('--output-prefix', default='heatmap', help='输出文件前缀（不含扩展名）')
    parser.add_argument('--output-dir', default=None, help='输出目录（默认写入便携版 Chart/correlation_heatmap 下）')
    parser.add_argument('--figsize', type=parse_figsize, default=DEFAULT_FIGSIZE, help='图尺寸，格式为"宽,高"，默认6.02,5.20')

    args = parser.parse_args()

    setup_matplotlib()

    df = load_csv(args.csv_file)

    # 自动检测数值列
    columns = get_numeric_columns(df)

    if len(columns) < 2:
        raise RuntimeError('错误：需要至少2个数值列进行分析')

    print(f"\n将分析以下列: {columns}")

    # 计算默认输出目录
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        script_dir = Path(__file__).parent
        out_dir = script_dir.parent / 'Chart' / 'correlation_heatmap'

    correlation_heatmap(
        df,
        columns,
        method=METHOD,
        output_prefix=str(out_dir / args.output_prefix),
        keep_labels=KEEP_LABELS,
        x_rot=X_ROT,
        y_rot=Y_ROT,
        figsize=args.figsize,
        show=False,
    )


if __name__ == '__main__':
    main()