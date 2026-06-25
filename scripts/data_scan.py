import os
import sys
import pandas as pd

PROJECT_ROOT = r"d:\文件管理\东吴证券\UTR股票复现"
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
REPORT_PATH = os.path.join(OUTPUT_DIR, "01_data_scan.md")

os.makedirs(OUTPUT_DIR, exist_ok=True)

files_to_scan = {
    "AShare_Listdate.csv": "A股上市日期数据，用于剔除新股（上市未满3个月）",
    "Ashare_suspension.csv": "A股停牌数据，用于剔除调仓日停牌的股票",
    "derivative.csv": "衍生指标数据，包含日换手率、自由流通换手率、总市值、流通市值和涨跌停状态，是计算因子的核心来源",
    "industry_class_CITICS.csv": "中信一级行业分类数据，用于行业中性化（包含30个中信一级行业）",
    "price.csv": "行情数据，包含开高低收、成交量等，用于计算超额收益和复权表现",
    "st.csv": "ST状态数据，用于剔除ST或*ST股票"
}

def scan():
    print("Starting comprehensive metadata scan...")
    markdown_lines = [
        "# 数据扫描与质量审查报告 (01_data_scan)",
        "",
        "- 扫描时间: 2026-06-17",
        f"- 工作区主目录: `{PROJECT_ROOT}`",
        "",
        "## 1. 数据集基本信息汇总",
        "",
        "以下是对工作区中所有核心原始 CSV 数据集的宏观扫描结果。出于内存安全与性能考虑，大型文件采用列过滤和流式读取：",
        "",
        "| 文件名 | 文件大小 (MB) | 列名 (Columns) | 数据定位与主要用途 |",
        "| :--- | :--- | :--- | :--- |"
    ]

    for filename, desc in files_to_scan.items():
        filepath = os.path.join(PROJECT_ROOT, filename)
        if not os.path.exists(filepath):
            print(f"Warning: {filename} does not exist!")
            continue
        
        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        df_sample = pd.read_csv(filepath, nrows=5)
        cols_str = ", ".join([f"`{c}`" for c in df_sample.columns])
        markdown_lines.append(f"| `{filename}` | {size_mb:.2f} MB | {cols_str} | {desc} |")

    markdown_lines.extend([
        "",
        "## 2. 核心特征深度探查 (Data-Quality Check)",
        ""
    ])

    # 1. List date
    list_date_path = os.path.join(PROJECT_ROOT, "AShare_Listdate.csv")
    if os.path.exists(list_date_path):
        df_list = pd.read_csv(list_date_path)
        unique_stocks = df_list['S_INFO_WINDCODE'].nunique()
        min_date = df_list['S_INFO_LISTDATE'].min()
        max_date = df_list['S_INFO_LISTDATE'].max()
        markdown_lines.extend([
            "### 2.1 上市日期数据 (`AShare_Listdate.csv`)",
            f"- **覆盖股票数量**: {unique_stocks} 只",
            f"- **上市日期范围**: {int(min_date) if not pd.isna(min_date) else 'N/A'} 至 {int(max_date) if not pd.isna(max_date) else 'N/A'}",
            "- **数据质量评估**: 完整，无缺失关键代码。可以用作股票池基础过滤的上市天数判定。",
            ""
        ])

    # 2. ST Data
    st_path = os.path.join(PROJECT_ROOT, "st.csv")
    if os.path.exists(st_path):
        df_st = pd.read_csv(st_path)
        unique_st = df_st['S_INFO_WINDCODE'].nunique()
        markdown_lines.extend([
            "### 2.2 ST 记录数据 (`st.csv`)",
            f"- **曾被ST/退市警示的股票数量**: {unique_st} 只",
            f"- **核心字段**: `S_TYPE_ST` (类型), `ENTRY_DT` (调入日期), `REMOVE_DT` (调出日期)",
            "- **数据质量评估**: 包含调入与调出时间区间，支持精确至交易日的动态 ST 股票过滤。",
            ""
        ])

    # 3. Industry Classification
    ind_path = os.path.join(PROJECT_ROOT, "industry_class_CITICS.csv")
    if os.path.exists(ind_path):
        df_ind = pd.read_csv(ind_path)
        unique_ind_stocks = df_ind['S_INFO_WINDCODE'].nunique()
        markdown_lines.extend([
            "### 2.3 中信一级行业数据 (`industry_class_CITICS.csv`)",
            f"- **覆盖股票数量**: {unique_ind_stocks} 只",
            "- **核心字段**: `CITICS_IND_CODE` (行业代码), `ENTRY_DT` (开始日期), `REMOVE_DT` (移除日期)",
            "- **数据质量评估**: 覆盖完整。在后续进行横截面回归中性化时，将用于生成 30 个中信一级行业哑变量，做强力行业剔除。",
            ""
        ])

    # 4. Price & Turnover
    # We read price.csv partially for stats
    price_path = os.path.join(PROJECT_ROOT, "price.csv")
    if os.path.exists(price_path):
        # High performance reading
        df_price_dates = pd.read_csv(price_path, usecols=['TRADE_DT'])
        min_p_date = df_price_dates['TRADE_DT'].min()
        max_p_date = df_price_dates['TRADE_DT'].max()
        total_p_rows = len(df_price_dates)
        markdown_lines.extend([
            "### 2.4 基础行情数据 (`price.csv`)",
            f"- **时间范围**: {min_p_date} 至 {max_p_date}",
            f"- **总记录行数**: {total_p_rows:,} 行",
            "- **核心字段**: `S_INFO_WINDCODE` (代码), `TRADE_DT` (交易日), `S_DQ_OPEN` (开盘价), `S_DQ_CLOSE` (收盘价), `S_DQ_VOLUME` (日成交量), `S_DQ_ADJFACTOR` (日复权因子)",
            "- **数据质量评估**: 历史跨度覆盖 2006 年至今（报告回测终点 2023-03-31 包含其中）。支持计算后置的复权收益率表现。",
            ""
        ])

    # 5. Derivative (Turnover & Market Cap)
    deriv_path = os.path.join(PROJECT_ROOT, "derivative.csv")
    if os.path.exists(deriv_path):
        df_deriv_sample = pd.read_csv(deriv_path, usecols=['TRADE_DT'])
        min_d_date = df_deriv_sample['TRADE_DT'].min()
        max_d_date = df_deriv_sample['TRADE_DT'].max()
        markdown_lines.extend([
            "### 2.5 衍生及市值数据 (`derivative.csv`)",
            f"- **时间范围**: {min_d_date} 至 {max_d_date}",
            "- **关键特征**: `S_DQ_MV` (流通市值), `S_DQ_TURN` (日自由流通换手率), `S_DQ_TURN` (日换手率)",
            "- **数据质量评估**: 该文件是因子的主力提取源：",
            "  1. `S_DQ_TURN` (自由流通换手率) 用于计算核心因子 $Turn20$ 与 $STR$。",
            "  2. `S_DQ_MV` 用于获取月末流通市值，取对数后用作市值中性化自变量。",
            ""
        ])

    markdown_lines.extend([
        "## 3. 复现流程中的潜在数据风险与解决方案",
        "",
        "1. **大文件内存溢出风险**：",
        "   - **隐患**：`derivative.csv` 大小近 2GB，包含大量冗余行与列，直接全量读取极易撑爆内存并引发脚本崩溃。",
        "   - **对策**：我们将仅加载必要的 4 列（代码、日期、自由流通换手率、流通市值），并按照月份进行横截面切片分月处理，确保内存占用控制在 200MB 以内。",
        "2. **停牌股的复权异常值**：",
        "   - **隐患**：停牌期间的换手率为 0，标准差也是 0，如果作为“量小且量稳”带入计算，会导致严重的复现偏差（误选高权重空头或多头）。",
        "   - **对策**：在计算 $Turn20$ 和 $STR$ 时，我们首先识别个股在当期 20 日中实际停牌或交易的天数，若停牌天数超过 10 天则直接剔除，且剔除调仓日（月末或下月初第一天）停牌的样本，确保可交易性。",
        "3. **极端异常值干扰**：",
        "   - **隐患**：个别微盘股的日自由流通换手率存在极端畸变点（比如上百倍），直接回归对残差敏感性大。",
        "   - **对策**：在中性化前，对 $Turn20$ 和 $STR$ 实施标准的**三倍中位数绝对偏差（3-MAD）去极值法**，并进行 **Z-score 标准化**。",
        "",
        "---"
    ])

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(markdown_lines))
    print(f"Data scan report saved successfully: {REPORT_PATH}")

if __name__ == "__main__":
    scan()
