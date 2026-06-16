import io
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

# =========================
# Matplotlib 中文字体设置
# 解决图表标题、坐标轴、标签显示为方框的问题
# Windows 优先使用 Microsoft YaHei；如不可用，再尝试 SimHei。
# =========================
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False


st.set_page_config(page_title="平遥古城气候风险量化评估平台 V1.0", layout="wide")

def risk_level(value):
    if value < 0.2:
        return "低风险"
    elif value < 0.4:
        return "较低风险"
    elif value < 0.6:
        return "中风险"
    elif value < 0.8:
        return "较高风险"
    else:
        return "高风险"

def calc_cdd(precip, threshold=1.0):
    max_run, current = 0, 0
    for p in precip:
        if pd.isna(p):
            current = 0
        elif p < threshold:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run

def calc_cwd(precip, threshold=1.0):
    max_run, current = 0, 0
    for p in precip:
        if pd.isna(p):
            current = 0
        elif p >= threshold:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run

def calc_wsdi(tmax, base_p90):
    above = tmax > base_p90
    total, run = 0, 0
    for val in above:
        if val:
            run += 1
        else:
            if run >= 6:
                total += run
            run = 0
    if run >= 6:
        total += run
    return total

def calc_csdi(tmin, base_p10):
    below = tmin < base_p10
    total, run = 0, 0
    for val in below:
        if val:
            run += 1
        else:
            if run >= 6:
                total += run
            run = 0
    if run >= 6:
        total += run
    return total

def calc_rx5day(precip):
    s = pd.Series(precip).rolling(5, min_periods=5).sum()
    return np.nan if s.dropna().empty else float(s.max())

def calc_climate_indices(df, date_col, tmax_col, tmin_col, pre_col):
    data = df.copy()
    data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
    data = data.dropna(subset=[date_col]).sort_values(date_col)
    tmax = pd.to_numeric(data[tmax_col], errors="coerce")
    tmin = pd.to_numeric(data[tmin_col], errors="coerce")
    pre = pd.to_numeric(data[pre_col], errors="coerce").fillna(0)

    tx90 = np.nanpercentile(tmax, 90)
    tn90 = np.nanpercentile(tmin, 90)
    tx10 = np.nanpercentile(tmax, 10)
    tn10 = np.nanpercentile(tmin, 10)
    wet = pre[pre >= 1]
    p95 = np.nanpercentile(wet, 95) if len(wet) > 0 else np.nan
    p99 = np.nanpercentile(wet, 99) if len(wet) > 0 else np.nan

    indicators = {
        "TX90p_高温日比例_%": float((tmax > tx90).mean() * 100),
        "TN90p_暖夜比例_%": float((tmin > tn90).mean() * 100),
        "WSDI_暖持续期天数": float(calc_wsdi(tmax.values, tx90)),
        "Rx1day_最大1日降水_mm": float(pre.max()),
        "Rx5day_最大连续5日降水_mm": calc_rx5day(pre.values),
        "R95p_强降水总量_mm": float(pre[pre > p95].sum()) if not pd.isna(p95) else np.nan,
        "R99p_极端强降水总量_mm": float(pre[pre > p99].sum()) if not pd.isna(p99) else np.nan,
        "CDD_连续干日数": float(calc_cdd(pre.values)),
        "CWD_连续湿润日数": float(calc_cwd(pre.values)),
        "TX10p_冷昼比例_%": float((tmax < tx10).mean() * 100),
        "TN10p_冷夜比例_%": float((tmin < tn10).mean() * 100),
        "CSDI_冷持续期天数": float(calc_csdi(tmin.values, tn10)),
        "冻融日数": float(((tmax > 0) & (tmin < 0)).sum()),
        "平均气温_℃": float(((tmax + tmin) / 2).mean()),
        "总降水量_mm": float(pre.sum())
    }
    return pd.DataFrame({"指标": list(indicators.keys()), "数值": list(indicators.values())})

def make_result_excel(results_df, climate_df=None):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        results_df.to_excel(writer, sheet_name="风险计算结果", index=False)
        if climate_df is not None:
            climate_df.to_excel(writer, sheet_name="气候指标计算结果", index=False)
    output.seek(0)
    return output

st.title("平遥古城人居环境及基础设施气候风险量化评估平台 V1.0")
st.write("用于演示 H 气候危险性、E 暴露度、V 脆弱性、AC 适应力框架下的综合风险计算。")

st.sidebar.header("综合风险权重设置")
wH = st.sidebar.number_input("H 气候危险性权重", 0.0, 1.0, 0.35, 0.01)
wE = st.sidebar.number_input("E 暴露度权重", 0.0, 1.0, 0.25, 0.01)
wV = st.sidebar.number_input("V 脆弱性权重", 0.0, 1.0, 0.25, 0.01)
wAC = st.sidebar.number_input("AC 适应力不足权重", 0.0, 1.0, 0.15, 0.01)
weight_sum = wH + wE + wV + wAC
st.sidebar.write(f"当前权重合计：{weight_sum:.2f}")
if weight_sum > 0 and abs(weight_sum - 1.0) > 0.001:
    st.sidebar.warning("权重合计不等于 1，已自动按比例归一化。")
    wH, wE, wV, wAC = wH/weight_sum, wE/weight_sum, wV/weight_sum, wAC/weight_sum

tab1, tab2, tab3, tab4 = st.tabs(["1 数据上传", "2 气候指标计算", "3 H-E-V-AC 输入", "4 结果输出"])

with tab1:
    st.header("1 数据上传")
    uploaded_excel = st.file_uploader("上传平遥古城气候风险案例数据收集表", type=["xlsx"])
    if uploaded_excel is not None:
        try:
            excel_data = pd.read_excel(uploaded_excel, sheet_name=None)
            st.success("Excel 上传成功")
            st.write("识别到工作表：", list(excel_data.keys()))
            sheet = st.selectbox("选择工作表预览", list(excel_data.keys()))
            st.dataframe(excel_data[sheet], use_container_width=True)
        except Exception as e:
            st.error(f"读取 Excel 失败：{e}")
    else:
        st.info("可先不上传 Excel，直接在第 3 页手动输入 H/E/V/AC。")

with tab2:
    st.header("2 气候指标计算")
    st.write("上传逐日气候数据，至少包含日期、最高气温、最低气温、降水量。")
    climate_file = st.file_uploader("上传逐日气候数据 CSV 或 Excel", type=["csv", "xlsx"], key="climate")
    if climate_file is not None:
        try:
            climate_df = pd.read_csv(climate_file) if climate_file.name.lower().endswith(".csv") else pd.read_excel(climate_file)
            st.dataframe(climate_df.head(), use_container_width=True)
            cols = climate_df.columns.tolist()
            c1, c2, c3, c4 = st.columns(4)
            date_col = c1.selectbox("日期列", cols)
            tmax_col = c2.selectbox("最高气温列", cols)
            tmin_col = c3.selectbox("最低气温列", cols)
            pre_col = c4.selectbox("降水量列", cols)
            if st.button("计算气候指标"):
                climate_result = calc_climate_indices(climate_df, date_col, tmax_col, tmin_col, pre_col)
                st.session_state["climate_result"] = climate_result
                st.success("气候指标计算完成")
                st.dataframe(climate_result, use_container_width=True)
        except Exception as e:
            st.error(f"气候数据处理失败：{e}")
    if "climate_result" in st.session_state:
        st.subheader("已计算气候指标")
        st.dataframe(st.session_state["climate_result"], use_container_width=True)

with tab3:
    st.header("3 H-E-V-AC 输入与计算")
    st.info("单个案例 V1.0 暂采用 0—1 分值输入。0 表示最低，1 表示最高。")

    st.subheader("气候危险性 H")
    H_heat = st.slider("高温热浪危险性", 0.0, 1.0, 0.60, 0.01)
    H_flood = st.slider("暴雨洪涝危险性", 0.0, 1.0, 0.70, 0.01)
    H_rain = st.slider("连续降雨危险性", 0.0, 1.0, 0.65, 0.01)
    H_drought = st.slider("干旱缺水危险性", 0.0, 1.0, 0.45, 0.01)
    H_freeze = st.slider("低温冻融危险性", 0.0, 1.0, 0.50, 0.01)
    H = np.mean([H_heat, H_flood, H_rain, H_drought, H_freeze])

    st.subheader("暴露度 E")
    E_population = st.slider("人口与游客暴露", 0.0, 1.0, 0.70, 0.01)
    E_building = st.slider("传统建筑与老旧建筑暴露", 0.0, 1.0, 0.80, 0.01)
    E_infra = st.slider("道路与基础设施暴露", 0.0, 1.0, 0.60, 0.01)
    E_service = st.slider("公共服务设施暴露", 0.0, 1.0, 0.55, 0.01)
    E = np.mean([E_population, E_building, E_infra, E_service])

    st.subheader("脆弱性 V")
    V_building = st.slider("建筑脆弱性", 0.0, 1.0, 0.80, 0.01)
    V_drainage = st.slider("排水脆弱性", 0.0, 1.0, 0.70, 0.01)
    V_social = st.slider("社会脆弱性", 0.0, 1.0, 0.55, 0.01)
    V_ecology = st.slider("生态调节脆弱性", 0.0, 1.0, 0.60, 0.01)
    V_traffic = st.slider("交通与消防通道脆弱性", 0.0, 1.0, 0.65, 0.01)
    V = np.mean([V_building, V_drainage, V_social, V_ecology, V_traffic])

    st.subheader("适应力 AC")
    AC_engineering = st.slider("工程适应力", 0.0, 1.0, 0.45, 0.01)
    AC_ecology = st.slider("生态适应力", 0.0, 1.0, 0.40, 0.01)
    AC_emergency = st.slider("应急适应力", 0.0, 1.0, 0.55, 0.01)
    AC_service = st.slider("公共服务适应力", 0.0, 1.0, 0.50, 0.01)
    AC_governance = st.slider("治理适应力", 0.0, 1.0, 0.60, 0.01)
    AC = np.mean([AC_engineering, AC_ecology, AC_emergency, AC_service, AC_governance])

    R = wH * H + wE * E + wV * V + wAC * (1 - AC)
    st.session_state["risk_result"] = {
        "H 气候危险性": H,
        "E 暴露度": E,
        "V 脆弱性": V,
        "AC 适应力": AC,
        "1-AC 适应能力不足": 1 - AC,
        "R 综合气候风险": R,
        "风险等级": risk_level(R)
    }
    st.metric("综合气候风险指数 R", f"{R:.3f}", risk_level(R))

with tab4:
    st.header("4 结果输出")
    if "risk_result" not in st.session_state:
        st.info("请先在第 3 页完成计算。")
    else:
        result = st.session_state["risk_result"]
        result_df = pd.DataFrame({"项目": list(result.keys()), "结果": list(result.values())})
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("H", f"{result['H 气候危险性']:.3f}")
        c2.metric("E", f"{result['E 暴露度']:.3f}")
        c3.metric("V", f"{result['V 脆弱性']:.3f}")
        c4.metric("AC", f"{result['AC 适应力']:.3f}")
        c5.metric("R", f"{result['R 综合气候风险']:.3f}", result["风险等级"])

        st.dataframe(result_df, use_container_width=True)

        chart_df = pd.DataFrame({
            "维度": ["H 气候危险性", "E 暴露度", "V 脆弱性", "1-AC 适应能力不足"],
            "指数值": [result["H 气候危险性"], result["E 暴露度"], result["V 脆弱性"], result["1-AC 适应能力不足"]]
        })
        fig, ax = plt.subplots()
        ax.bar(chart_df["维度"], chart_df["指数值"])
        ax.set_ylim(0, 1)
        ax.set_ylabel("指数值")
        ax.set_title("平遥古城气候风险结构")
        plt.xticks(rotation=20, ha="right")
        st.pyplot(fig)

        conclusion = f"""
        平遥古城及周边人居空间综合气候风险指数为 {result['R 综合气候风险']:.3f}，
        风险等级为“{result['风险等级']}”。从风险结构看，气候危险性为 {result['H 气候危险性']:.3f}，
        暴露度为 {result['E 暴露度']:.3f}，脆弱性为 {result['V 脆弱性']:.3f}，
        适应力为 {result['AC 适应力']:.3f}，适应能力不足为 {result['1-AC 适应能力不足']:.3f}。
        后续应重点结合暴雨内涝、连续降雨建筑潮湿、高温热浪和游客高暴露等影响链，
        进一步识别排水系统、传统建筑修缮、游客疏散、应急避难和预警响应方面的适应短板。
        """
        st.subheader("自动文字结论")
        st.write(conclusion)

        output = make_result_excel(result_df, st.session_state.get("climate_result", None))
        st.download_button(
            label="下载风险计算结果 Excel",
            data=output,
            file_name="平遥古城气候风险计算结果.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
