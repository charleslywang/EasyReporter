# -*- coding: utf-8 -*-
"""
根据 CSV 生成两两组合的线性相关散点图 (PDF)。
支持自定义列名、图片大小、散点颜色
"""
import os
import sys
import argparse
import itertools
import io

# Windows控制台UTF-8支持
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 尝试导入依赖
try:
    import pandas as pd
    import seaborn as sns
    import matplotlib.pyplot as plt
    from scipy import stats
    import numpy as np
except ImportError as e:
    missing = str(e)
    sys.stderr.write(f"依赖未安装: {missing}\n请先安装: pip install pandas seaborn matplotlib scipy numpy\n")
    sys.exit(1)

# ============================================================
# 全局字体与样式设置
# ============================================================
plt.rcParams.update({
    'font.family': 'DejaVu Sans',  # Linux 通用字体
    'font.size': 35,
    'axes.titlesize': 35,
    'axes.labelsize': 35,
    'xtick.labelsize': 35,
    'ytick.labelsize': 35,
    'legend.fontsize': 35,
    'figure.titlesize': 35,
    'axes.linewidth': 1,
    'pdf.fonttype': 42,
    'ps.fonttype': 42,
    'axes.unicode_minus': False,
})

def clean_label(label):
    """去除列名中的括号及括号内内容,用作坐标轴标签"""
    import re
    return re.sub(r'\([^)]*\)', '', label).strip()

def read_data(csv_path: str):
    """读取CSV并清洗数据"""
    encodings = ["utf-8-sig", "utf-8", "gbk", "gb2312", "latin1"]
    last_err = None
    df = None
    for enc in encodings:
        try:
            df = pd.read_csv(csv_path, encoding=enc, engine='python', sep=None)
            if len(df.columns) < 5:
                raise ValueError("Incorrect separator")
            break
        except Exception as err1:
            last_err = err1
            try:
                df = pd.read_csv(csv_path, encoding=enc, engine='python', sep=',')
                break
            except Exception as err2:
                last_err = err2
                try:
                    df = pd.read_csv(csv_path, encoding=enc, engine='c', sep=',')
                    break
                except Exception as err3:
                    last_err = err3
                    df = None
                    continue
    if df is None:
        raise RuntimeError(f"无法读取CSV: {csv_path}. 错误: {last_err}")

    cols = list(df.columns)
    if len(cols) < 5:
        raise ValueError("CSV 列数不足，期望至少5列: [Target, ID, FACS, AI, Amplicon]")

    df = df.rename(columns={cols[0]: "Target", cols[1]: "ID"})
    num_cols = cols[2:5]

    for c in num_cols:
        df[c] = (
            df[c]
            .astype(str)
            .str.strip()
            .str.replace('%', '', regex=False)
            .str.replace('\u3000', '', regex=False)
        )
        df[c] = pd.to_numeric(df[c], errors='coerce')

    pretty_map = {}
    for c in num_cols:
        lc = c.lower()
        if "fac" in lc:
            pretty_map[c] = "FACS"
        elif lc.startswith("ai") or "ai(" in lc:
            pretty_map[c] = "AI"
        elif "sv" in lc or "amplicon" in lc:
            pretty_map[c] = "Amplicon"
        else:
            pretty_map[c] = c.split('(')[0].strip()

    return df, num_cols, pretty_map

def plot_scatter_matrix(df: pd.DataFrame, num_cols, pretty_map, out_dir: str, 
                        csv_path: str, figsize=(8, 8), colors=None):
    """绘制两两组合的散点图，每张图单独保存"""
    if colors is None:
        colors = ['#37AB7B', '#F94141', '#589FF3']
    
    data = df[num_cols].dropna(how='any')
    if data.empty:
        raise ValueError("数值列数据为空或全为NaN，无法绘图。")

    # 全局统一设置
    UNIFIED_COLOR = '#595757'   # 回归线、散点边框、坐标轴边框、刻度、标签、Spearman ρ²
    LINE_WIDTH = 1.5             # 所有线条粗细

    col_pairs = list(itertools.combinations(num_cols, 2))

    for i, (x_col, y_col) in enumerate(col_pairs, 1):
        # 为每组使用不同颜色
        point_color = colors[i - 1] if i - 1 < len(colors) else colors[0]
        
        fig, ax = plt.subplots(figsize=figsize, dpi=600)

        # 绘制回归线和散点
        sns.regplot(
            x=data[x_col], y=data[y_col], ax=ax,
            fit_reg=True, ci=None, color=point_color,
            scatter_kws={'alpha': 1.0, 's': 250, 'edgecolor': UNIFIED_COLOR},
            line_kws={'color': UNIFIED_COLOR, 'linewidth': LINE_WIDTH}
        )

        # Spearman ρ² - 去除边框
        rho, _ = stats.spearmanr(data[x_col], data[y_col])
        rho2 = rho ** 2
        ax.text(
            0.05, 0.95,
            f"Spearman ρ²={rho2:.2f}",
            transform=ax.transAxes,
            fontsize=22,
            color=UNIFIED_COLOR,
            verticalalignment='top',
            bbox=None  # 去除边框
        )

        # 坐标轴标签 - 使用clean_label去除括号
        ax.set_xlabel(clean_label(pretty_map.get(x_col, x_col)), color=UNIFIED_COLOR)
        ax.set_ylabel(clean_label(pretty_map.get(y_col, y_col)), color=UNIFIED_COLOR)

        # 坐标轴样式
        ax.tick_params(axis='both', colors=UNIFIED_COLOR, width=LINE_WIDTH)
        for spine in ax.spines.values():
            spine.set_color(UNIFIED_COLOR)
            spine.set_linewidth(LINE_WIDTH)

        plt.tight_layout()
        
        # 生成输出文件名
        basename = os.path.splitext(os.path.basename(csv_path))[0]
        out_single = os.path.join(out_dir, f'{basename}_{i:02d}.pdf')
        plt.savefig(out_single, format="pdf", bbox_inches="tight")
        plt.close()
        print(f"✅ 已生成散点图: {out_single}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='相关性散点图（Spearman）生成器')
    parser.add_argument('csv_file', help='CSV文件路径')
    # 列名参数
    parser.add_argument('--green-x', default='FACS(%)')
    parser.add_argument('--green-y', default='AI(%)')
    parser.add_argument('--red-x', default='FACS(%)')
    parser.add_argument('--red-y', default='Amplicon(%)')
    parser.add_argument('--te-x', default='AI(%)')
    parser.add_argument('--te-y', default='Amplicon(%)')
    # 图片参数
    parser.add_argument('--figsize-width', type=float, default=8.0, help='图片宽度(英寸)')
    parser.add_argument('--figsize-height', type=float, default=8.0, help='图片高度(英寸)')
    parser.add_argument('--color1', default='#37AB7B', help='第一组散点图颜色')
    parser.add_argument('--color2', default='#F94141', help='第二组散点图颜色')
    parser.add_argument('--color3', default='#589FF3', help='第三组散点图颜色')
    parser.add_argument('--output-dir', default=None, help='输出目录')

    args = parser.parse_args()
    csv_file = args.csv_file
    
    if not os.path.exists(csv_file):
        sys.stderr.write(f"未找到文件: {csv_file}\n")
        sys.exit(1)

    try:
        df, num_cols, pretty_map = read_data(csv_file)
        
        # 确定输出目录
        if args.output_dir:
            out_dir = args.output_dir
        else:
            out_dir = os.path.dirname(csv_file)
        
        os.makedirs(out_dir, exist_ok=True)
        
        # 准备参数
        figsize = (args.figsize_width, args.figsize_height)
        colors = [args.color1, args.color2, args.color3]
        
        plot_scatter_matrix(df, num_cols, pretty_map, out_dir, csv_file, figsize, colors)
        print(f"✅ 所有散点图已保存至: {out_dir}")
    except Exception as e:
        sys.stderr.write(f"处理失败: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)

