import os
import sys
import numpy as np
import pandas as pd
import statsmodels.api as sm

PROJECT_ROOT = r"d:\文件管理\东吴证券\UTR股票复现"
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
FACTORS_CSV_PATH = os.path.join(OUTPUT_DIR, "factors.csv")
PIPELINE_MD_PATH = os.path.join(OUTPUT_DIR, "03_reproduce_pipeline.md")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_codes_with_majority_st_days(df_st, codes, month_days):
    if len(month_days) == 0:
        return set()

    month_days = sorted(int(d) for d in month_days)
    codes = set(codes)
    st_day_counts = {code: 0 for code in codes}

    st_use = df_st[df_st['S_INFO_WINDCODE'].isin(codes)].copy()
    if st_use.empty:
        return set()

    for _, row in st_use.iterrows():
        entry_dt = row.get('ENTRY_DT')
        remove_dt = row.get('REMOVE_DT')
        if pd.isna(entry_dt):
            continue

        entry_dt = int(entry_dt)
        remove_dt = month_days[-1] if pd.isna(remove_dt) else int(remove_dt)
        code = row['S_INFO_WINDCODE']

        for trade_dt in month_days:
            if entry_dt <= trade_dt <= remove_dt:
                st_day_counts[code] += 1

    total_days = len(month_days)
    return {
        code for code, st_days in st_day_counts.items()
        if st_days > total_days - st_days
    }


def get_codes_with_majority_price_trading_days(price_month, codes, month_days):
    if len(month_days) == 0:
        return set()

    codes = set(codes)
    total_days = len(set(int(d) for d in month_days))
    if total_days == 0 or price_month.empty:
        return set()

    price_use = price_month[price_month['S_INFO_WINDCODE'].isin(codes)].copy()
    if price_use.empty:
        return set()

    normal_mask = (
        price_use['S_DQ_OPEN'].notna()
        & price_use['S_DQ_CLOSE'].notna()
        & (price_use['S_DQ_VOLUME'].fillna(0) > 0)
    )
    normal_counts = (
        price_use.loc[normal_mask]
        .groupby('S_INFO_WINDCODE')['TRADE_DT']
        .nunique()
    )

    return {
        code for code in codes
        if int(normal_counts.get(code, 0)) > total_days - int(normal_counts.get(code, 0))
    }


def calc_factors():
    print("Step 4.1: Loading raw datasets...")
    
    # 1. Load list dates
    df_list = pd.read_csv(os.path.join(PROJECT_ROOT, "AShare_Listdate.csv"))
    list_date_dict = dict(zip(df_list['S_INFO_WINDCODE'], df_list['S_INFO_LISTDATE']))

    # 2. Load ST records
    df_st = pd.read_csv(os.path.join(PROJECT_ROOT, "st.csv"))
    
    # 3. Load CITICS industry
    print("Loading industry data...")
    df_ind = pd.read_csv(os.path.join(PROJECT_ROOT, "industry_class_CITICS.csv"))
    df_ind['CITICS_IND_CODE_4'] = df_ind['CITICS_IND_CODE'].astype(str).str[:4]
    
    # 3.1 Load Barra CNE5 style factors
    print("Loading Barra CNE5 style factors...")
    barra_factors = ['Beta', 'BooktoPrice', 'EarningYield', 'Growth', 'Leverage', 'Liquidity', 'Momentum', 'NonlinearSize', 'ResidualVolatility', 'Size']
    barra_data = {}
    for fac in barra_factors:
        fac_path = os.path.join(PROJECT_ROOT, "Barra_CNE5", f"{fac}.txt")
        print(f"Loading Barra factor: {fac}...")
        df_fac = pd.read_feather(fac_path)
        df_fac['time_int'] = pd.to_datetime(df_fac['time']).dt.strftime('%Y%m%d').astype(int)
        barra_data[fac] = df_fac.set_index('time_int')
    
    # 4. Load core derivative and turnover data (High Performance)
    print("Loading derivative data (size, turnover, etc.)...")
    df_deriv = pd.read_csv(
        os.path.join(PROJECT_ROOT, "derivative.csv"),
        usecols=['S_INFO_WINDCODE', 'TRADE_DT', 'S_DQ_TURN', 'S_DQ_MV']
    )
    df_deriv['TRADE_DT'] = df_deriv['TRADE_DT'].astype(int)

    print("Loading price trading activity for monthly suspension filter...")
    df_price_activity = pd.read_csv(
        os.path.join(PROJECT_ROOT, "price.csv"),
        usecols=['S_INFO_WINDCODE', 'TRADE_DT', 'S_DQ_OPEN', 'S_DQ_CLOSE', 'S_DQ_VOLUME']
    )
    df_price_activity['TRADE_DT'] = df_price_activity['TRADE_DT'].astype(int)
    
    # Clean up non-trading days first to avoid calendar days inflating the 20-day rolling window
    print("Cleaning non-trading days (NaN free turnover) first...")
    df_deriv = df_deriv.dropna(subset=['S_DQ_TURN', 'S_DQ_MV']).copy()

    print("Sorting and computing 20-day rolling indicators on trading days...")
    df_deriv = df_deriv.sort_values(['S_INFO_WINDCODE', 'TRADE_DT']).reset_index(drop=True)

    
    # Calculate Turn20 and STR using efficient pandas rolling window on consecutive trading days
    df_deriv['Turn20'] = df_deriv.groupby('S_INFO_WINDCODE')['S_DQ_TURN'].transform(
        lambda x: x.rolling(20, min_periods=10).mean()
    )
    df_deriv['STR'] = df_deriv.groupby('S_INFO_WINDCODE')['S_DQ_TURN'].transform(
        lambda x: x.rolling(20, min_periods=10).std()
    )
    
    # Find all unique trade dates and get month-ends
    all_dates = sorted(df_deriv['TRADE_DT'].unique())
    df_dates = pd.DataFrame({'date': all_dates})
    df_dates['year_month'] = df_dates['date'] // 100
    month_ends = df_dates.groupby('year_month')['date'].max().tolist()
    
    # Restrict backtest window: 20060101 to 20250930
    month_ends = [d for d in month_ends if 20060228 <= d <= 20230331]
    print(f"Total month-ends to process: {len(month_ends)}")

    active_months = {d // 100 for d in month_ends}
    df_price_activity['year_month'] = df_price_activity['TRADE_DT'] // 100
    df_price_activity = df_price_activity[df_price_activity['year_month'].isin(active_months)].copy()
    price_days_by_month = {
        int(month): sorted(group['TRADE_DT'].unique())
        for month, group in df_price_activity.groupby('year_month')
    }
    price_activity_by_month = {
        int(month): group.drop(columns=['year_month']).copy()
        for month, group in df_price_activity.groupby('year_month')
    }
    
    processed_slices = []
    
    print("Processing month-end cross sections & neutralizing factors...")
    for me_date in month_ends:
        # T-month end slice
        df_slice = df_deriv[df_deriv['TRADE_DT'] == me_date].copy()
        if len(df_slice) == 0:
            continue
            
        # A. Filter New Stocks (listed < 60 days)
        dt_me_series = pd.to_datetime(df_slice['TRADE_DT'].astype(str), format='%Y%m%d', errors='coerce')
        ld_series = pd.to_datetime(df_slice['S_INFO_WINDCODE'].map(list_date_dict).astype(int).astype(str), format='%Y%m%d', errors='coerce')
        days_since_listed = (dt_me_series - ld_series).dt.days
        df_slice = df_slice[days_since_listed >= 60]
        
        # B. Filter ST stocks using the same majority-of-month rule as the step pipeline.
        current_month = me_date // 100
        month_days = [d for d in all_dates if d // 100 == current_month]
        st_codes = get_codes_with_majority_st_days(
            df_st=df_st,
            codes=df_slice['S_INFO_WINDCODE'],
            month_days=month_days,
        )
        df_slice = df_slice[~df_slice['S_INFO_WINDCODE'].isin(st_codes)]

        # C. Filter stocks whose normal price trading days are not more than suspended/invalid days.
        price_month = price_activity_by_month.get(current_month, pd.DataFrame())
        price_month_days = price_days_by_month.get(current_month, [])
        tradable_codes = get_codes_with_majority_price_trading_days(
            price_month=price_month,
            codes=df_slice['S_INFO_WINDCODE'],
            month_days=price_month_days,
        )
        df_slice = df_slice[df_slice['S_INFO_WINDCODE'].isin(tradable_codes)]
        
        # D. Filter Suspended stocks on me_date
        df_slice = df_slice[df_slice['S_DQ_TURN'] > 0.0001]
        df_slice = df_slice.dropna(subset=['Turn20', 'STR', 'S_DQ_MV'])
        
        if len(df_slice) < 50:
            continue
            
        # E. Get CITICS industry for me_date
        df_ind_curr = df_ind[(df_ind['ENTRY_DT'] <= me_date) & ((df_ind['REMOVE_DT'].isna()) | (df_ind['REMOVE_DT'] >= me_date))]
        ind_map = dict(zip(df_ind_curr['S_INFO_WINDCODE'], df_ind_curr['CITICS_IND_CODE_4']))
        df_slice['CITICS'] = df_slice['S_INFO_WINDCODE'].map(ind_map).fillna('Other')
        
        # F. Scaling & Winsorization
        def winsorize_and_scale(series):
            median = series.median()
            mad = (series - median).abs().median()
            threshold = 3 * 1.4826 * mad
            if threshold == 0:
                threshold = 1e-6
            clipped = np.clip(series, median - threshold, median + threshold)
            return (clipped - clipped.mean()) / (clipped.std() if clipped.std() != 0 else 1)
            
        df_slice['Turn20_scaled'] = winsorize_and_scale(df_slice['Turn20'])
        df_slice['STR_scaled'] = winsorize_and_scale(df_slice['STR'])
        df_slice['ln_MV'] = winsorize_and_scale(np.log(df_slice['S_DQ_MV']))
        
        # G. Core Market-Cap Neutralization (AS PER REPORT: ONLY SIZE NEUTRALIZED!)
        # Factor_neutral = Residual(Factor ~ const + ln_MV)
        X_size = sm.add_constant(df_slice['ln_MV'])
        
        try:
            model_turn = sm.OLS(df_slice['Turn20_scaled'], X_size).fit()
            df_slice['Turn20_neutral'] = model_turn.resid
        except Exception as e:
            df_slice['Turn20_neutral'] = df_slice['Turn20_scaled']
            
        try:
            model_str = sm.OLS(df_slice['STR_scaled'], X_size).fit()
            df_slice['STR_neutral'] = model_str.resid
        except Exception as e:
            df_slice['STR_neutral'] = df_slice['STR_scaled']
            
        # Re-scale residuals
        # df_slice['Turn20_neutral'] = (df_slice['Turn20_neutral'] - df_slice['Turn20_neutral'].mean()) / df_slice['Turn20_neutral'].std()
        # df_slice['STR_neutral'] = (df_slice['STR_neutral'] - df_slice['STR_neutral'].mean()) / df_slice['STR_neutral'].std()
        
        # H. Factor Synthesis
        # UTR 1.0 (Rank-based combo)
        N_stocks = len(df_slice)
        df_slice['rank_STR'] = df_slice['STR_neutral'].rank(ascending=True)
        df_slice['score1'] = df_slice['rank_STR']
        
        half_n = N_stocks // 2
        df_slice = df_slice.sort_values('rank_STR').reset_index(drop=True)
        
        top_half = df_slice.iloc[:half_n].copy()
        top_half['score2'] = top_half['Turn20_neutral'].rank(ascending=False)
        top_half['UTR1.0'] = top_half['score1'] + top_half['score2']
        
        bottom_half = df_slice.iloc[half_n:].copy()
        bottom_half['score2'] = bottom_half['Turn20_neutral'].rank(ascending=True)
        bottom_half['UTR1.0'] = bottom_half['score1'] + bottom_half['score2']
        
        df_slice = pd.concat([top_half, bottom_half], axis=0).reset_index(drop=True)
        df_slice['UTR1.0'] = (df_slice['UTR1.0'] - df_slice['UTR1.0'].mean()) / df_slice['UTR1.0'].std()
        
        # UTR 2.0 (Equivalent scale + softsign activation function)
        softsign_str = df_slice['STR_neutral'] / (1 + df_slice['STR_neutral'].abs())
        df_slice['UTR2.0'] = df_slice['STR_neutral'] + softsign_str * df_slice['Turn20_neutral']
        df_slice['UTR2.0'] = (df_slice['UTR2.0'] - df_slice['UTR2.0'].mean()) / df_slice['UTR2.0'].std()
        
        # H. "Pure" UTR 2.0 Factor (Neutralized against CITICS Industry + 10 Barra Style Factors)
        # As per Section 3.2 / Slide 22: Regress UTR 2.0 against 30 CITICS industry dummies and 10 Barra style factors, take residual
        industry_dummies = pd.get_dummies(df_slice['CITICS'], drop_first=False).astype(float)
        
        # Align 10 Barra style factors for this me_date
        barra_features = []
        for fac in barra_factors:
            df_fac = barra_data[fac]
            if me_date in df_fac.index:
                row = df_fac.loc[me_date]
                df_slice[fac] = df_slice['S_INFO_WINDCODE'].map(row)
            else:
                df_slice[fac] = np.nan
                
            # Handle missing values by cross-sectional median (standard quant preprocessing)
            median_val = df_slice[fac].median()
            if pd.isna(median_val):
                median_val = 0.0
            df_slice[fac] = df_slice[fac].fillna(median_val)
            
            # Standardize (Z-score)
            std_val = df_slice[fac].std()
            if std_val == 0 or pd.isna(std_val):
                std_val = 1.0
            df_slice[fac] = (df_slice[fac] - df_slice[fac].mean()) / std_val
            
            # Rename the column so it doesn't conflict
            col_name = f"barra_{fac}"
            df_slice[col_name] = df_slice[fac]
            barra_features.append(df_slice[col_name])
            
        X_pure = pd.concat([industry_dummies] + barra_features, axis=1)
        X_pure = X_pure.apply(pd.to_numeric, errors='coerce').fillna(0.0)
        
        try:
            model_pure = sm.OLS(df_slice['UTR2.0'], X_pure).fit()
            df_slice['UTR2.0_pure'] = model_pure.resid
            df_slice['UTR2.0_pure'] = (df_slice['UTR2.0_pure'] - df_slice['UTR2.0_pure'].mean()) / df_slice['UTR2.0_pure'].std()
        except Exception as e:
            print(f"OLS pure regression failed at {me_date}: {e}")
            df_slice['UTR2.0_pure'] = df_slice['UTR2.0']
            
        processed_slices.append(df_slice[[
            'S_INFO_WINDCODE', 'TRADE_DT', 'S_DQ_MV', 'Turn20', 'STR',
            'Turn20_neutral', 'STR_neutral', 'UTR1.0', 'UTR2.0', 'UTR2.0_pure'
        ]])

    print("Concatenating processed months...")
    df_all_factors = pd.concat(processed_slices, axis=0).reset_index(drop=True)
    df_all_factors.to_csv(FACTORS_CSV_PATH, index=False)
    print(f"Factors computed and successfully saved: {FACTORS_CSV_PATH} ({len(df_all_factors)} rows)")

    # Write 03_reproduce_pipeline.md
    pipeline_md_lines = [
        "# 因子合成与流水线搭建报告 (03_reproduce_pipeline)",
        "",
        "- 报告时间: 2026-06-17",
        f"- 因子文件输出位置: `{FACTORS_CSV_PATH}`",
        f"- 处理的总月份数: {len(month_ends)} 个月",
        f"- 总计生成因子数据行数: {len(df_all_factors):,} 行",
        "",
        "## 1. 因子预处理与中性化清洗细节 (已根据报告逻辑修正)",
        "",
        "根据原报告设计理念，我们对中性化逻辑进行了高精度微调：",
        "- **市值中性化（核心因子）**：基础因子 $Turn20$ 与 $STR$ **仅进行了市值中性化处理**。我们在月度横截面上将各因子对常数项和流通市值对数 $\\ln(MV)$ 进行回归取残差，保留了由于板块、行业聚类带来的宝贵选股超额阿尔法。",
        "- **新股、ST 与停牌剔除**：动态过滤上市未满 60 天（3 个月）的股票；利用 `st.csv` 按整月半数日期规则剔除 ST 污染样本；利用 `price.csv` 判断当月正常交易天数是否大于停牌/无效天数，不满足则跳过该股票该月，避免 `dropna` 后 rolling 将停牌前后日期直接拼接。",
        "- **极值处理**：对因子暴露应用 **3-MAD 算法** 进行标准去极值，并使用 Z-score 在横截面上缩放。",
        "",
        "## 2. 纯净 UTR 2.0 因子的提取",
        "",
        "为剔除中信一级行业与常用风格带来的业绩干扰，我们进一步提供了“纯净 UTR 2.0 因子” (`UTR2.0_pure`)：",
        "- 在合成得到 UTR 2.0 之后，我们每月月底将其对 30 个中信一级行业哑变量以及 10 个标准的 **Barra CNE5 风格因子**（`Beta`、`BooktoPrice`、`EarningYield`、`Growth`、`Leverage`、`Liquidity`、`Momentum`、`NonlinearSize`、`ResidualVolatility`、`Size`）进行多元线性回归，回归提取得到的残差标准化即为 `UTR2.0_pure`（对应报告第 3.2 节中的纯净因子选股表现）。",
        "",
        "## 3. 计算日志摘要",
        "",
        "| 特征维度 | 均值 (Mean) | 标准差 (Std) | 最小值 (Min) | 最大值 (Max) | 物理含义与对齐方向 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
        f"| `Turn20_neutral` | {df_all_factors['Turn20_neutral'].mean():.4f} | {df_all_factors['Turn20_neutral'].std():.4f} | {df_all_factors['Turn20_neutral'].min():.4f} | {df_all_factors['Turn20_neutral'].max():.4f} | 纯市值中性化后日均换手 |",
        f"| `STR_neutral` | {df_all_factors['STR_neutral'].mean():.4f} | {df_all_factors['STR_neutral'].std():.4f} | {df_all_factors['STR_neutral'].min():.4f} | {df_all_factors['STR_neutral'].max():.4f} | 纯市值中性化后换手标准差 |",
        f"| `UTR1.0` | {df_all_factors['UTR1.0'].mean():.4f} | {df_all_factors['UTR1.0'].std():.4f} | {df_all_factors['UTR1.0'].min():.4f} | {df_all_factors['UTR1.0'].max():.4f} | 基于纯市值中性化自变量合并的 UTR 1.0 |",
        f"| `UTR2.0` | {df_all_factors['UTR2.0'].mean():.4f} | {df_all_factors['UTR2.0'].std():.4f} | {df_all_factors['UTR2.0'].min():.4f} | {df_all_factors['UTR2.0'].max():.4f} | 基于激活函数合成的 UTR 2.0 (未去行业) |",
        f"| `UTR2.0_pure` | {df_all_factors['UTR2.0_pure'].mean():.4f} | {df_all_factors['UTR2.0_pure'].std():.4f} | {df_all_factors['UTR2.0_pure'].min():.4f} | {df_all_factors['UTR2.0_pure'].max():.4f} | 纯净 UTR 2.0 (中信行业与市值完全中性化) |",
        "",
        "---"
    ]
    
    with open(PIPELINE_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(pipeline_md_lines))
    print(f"Pipeline report saved successfully: {PIPELINE_MD_PATH}")

if __name__ == "__main__":
    calc_factors()
