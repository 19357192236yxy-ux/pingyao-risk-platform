
import io
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="平遥古城气候风险量化评估平台 V1.2", page_icon="🏛️", layout="wide", initial_sidebar_state="expanded")
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

st.markdown("""
<style>
.main-header{background:linear-gradient(90deg,#1f4e79 0%,#2f6f9f 100%);padding:24px 28px;border-radius:16px;color:white;margin-bottom:18px}.main-header h1{margin:0;font-size:34px;font-weight:700}.main-header p{margin-top:8px;font-size:16px;opacity:.95}.warning-card{background-color:#fff8e6;padding:14px 16px;border-left:5px solid #f59e0b;border-radius:10px;margin-bottom:12px}.risk-badge{color:white;padding:14px 18px;border-radius:14px;font-size:24px;text-align:center;font-weight:700;margin-bottom:12px}
</style>
""", unsafe_allow_html=True)

def risk_level(value):
    if value < 0.2: return "低风险"
    if value < 0.4: return "较低风险"
    if value < 0.6: return "中风险"
    if value < 0.8: return "较高风险"
    return "高风险"

def risk_color(level):
    return {"低风险":"#2E7D32","较低风险":"#66BB6A","中风险":"#FBC02D","较高风险":"#F57C00","高风险":"#C62828"}.get(level,"#64748b")

def show_risk_badge(level):
    st.markdown(f'<div class="risk-badge" style="background-color:{risk_color(level)};">综合风险等级：{level}</div>', unsafe_allow_html=True)

def calc_cdd(precip, threshold=1.0):
    max_run, current = 0, 0
    for p in precip:
        if pd.isna(p): current = 0
        elif p < threshold:
            current += 1; max_run = max(max_run, current)
        else: current = 0
    return max_run

def calc_cwd(precip, threshold=1.0):
    max_run, current = 0, 0
    for p in precip:
        if pd.isna(p): current = 0
        elif p >= threshold:
            current += 1; max_run = max(max_run, current)
        else: current = 0
    return max_run

def calc_wsdi(tmax, base_p90):
    above = tmax > base_p90; total, run = 0, 0
    for val in above:
        if val: run += 1
        else:
            if run >= 6: total += run
            run = 0
    if run >= 6: total += run
    return total

def calc_csdi(tmin, base_p10):
    below = tmin < base_p10; total, run = 0, 0
    for val in below:
        if val: run += 1
        else:
            if run >= 6: total += run
            run = 0
    if run >= 6: total += run
    return total

def calc_rx5day(precip):
    s = pd.Series(precip).rolling(5, min_periods=5).sum()
    return np.nan if s.dropna().empty else float(s.max())

def calc_climate_indices(df, date_col, tmax_col, tmin_col, pre_col):
    data = df.copy(); data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
    data = data.dropna(subset=[date_col]).sort_values(date_col)
    tmax = pd.to_numeric(data[tmax_col], errors="coerce")
    tmin = pd.to_numeric(data[tmin_col], errors="coerce")
    pre = pd.to_numeric(data[pre_col], errors="coerce").fillna(0)
    tx90, tn90 = np.nanpercentile(tmax,90), np.nanpercentile(tmin,90)
    tx10, tn10 = np.nanpercentile(tmax,10), np.nanpercentile(tmin,10)
    wet = pre[pre >= 1]
    p95 = np.nanpercentile(wet,95) if len(wet)>0 else np.nan
    p99 = np.nanpercentile(wet,99) if len(wet)>0 else np.nan
    indicators = {
        "TX90p_高温日比例_%": float((tmax > tx90).mean()*100),
        "TN90p_暖夜比例_%": float((tmin > tn90).mean()*100),
        "WSDI_暖持续期天数": float(calc_wsdi(tmax.values, tx90)),
        "Rx1day_最大1日降水_mm": float(pre.max()),
        "Rx5day_最大连续5日降水_mm": calc_rx5day(pre.values),
        "R95p_强降水总量_mm": float(pre[pre > p95].sum()) if not pd.isna(p95) else np.nan,
        "R99p_极端强降水总量_mm": float(pre[pre > p99].sum()) if not pd.isna(p99) else np.nan,
        "CDD_连续干日数": float(calc_cdd(pre.values)),
        "CWD_连续湿润日数": float(calc_cwd(pre.values)),
        "TX10p_冷昼比例_%": float((tmax < tx10).mean()*100),
        "TN10p_冷夜比例_%": float((tmin < tn10).mean()*100),
        "CSDI_冷持续期天数": float(calc_csdi(tmin.values, tn10)),
        "冻融日数": float(((tmax > 0) & (tmin < 0)).sum()),
        "平均气温_℃": float(((tmax+tmin)/2).mean()),
        "总降水量_mm": float(pre.sum())}
    meta = {"起始日期":data[date_col].min(),"结束日期":data[date_col].max(),"记录条数":len(data),"最高气温缺失数":int(tmax.isna().sum()),"最低气温缺失数":int(tmin.isna().sum()),"降水量缺失数":int(pd.to_numeric(data[pre_col], errors="coerce").isna().sum())}
    return pd.DataFrame({"指标": list(indicators.keys()), "数值": list(indicators.values())}), meta

def make_result_excel(results_df, climate_df=None, subrisk_df=None):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        results_df.to_excel(writer, sheet_name="综合风险结果", index=False)
        if subrisk_df is not None: subrisk_df.to_excel(writer, sheet_name="单灾种风险结果", index=False)
        if climate_df is not None: climate_df.to_excel(writer, sheet_name="气候指标计算结果", index=False)
    output.seek(0); return output

def plot_bar(chart_df):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=chart_df["维度"],
        y=chart_df["指数值"],
        text=[f"{v:.3f}" for v in chart_df["指数值"]],
        textposition="outside"
    ))
    fig.update_layout(
        title="平遥古城气候风险结构",
        yaxis_title="指数值",
        xaxis_title="风险成分",
        yaxis=dict(range=[0, 1]),
        height=430,
        margin=dict(l=40, r=30, t=70, b=80),
        font=dict(family="Microsoft YaHei, SimHei, Arial, sans-serif", size=14)
    )
    return fig

def plot_radar(labels, values):
    labels = list(labels)
    values = list(values)
    labels_closed = labels + labels[:1]
    values_closed = values + values[:1]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values_closed,
        theta=labels_closed,
        fill="toself",
        mode="lines+markers",
        name="风险结构"
    ))
    fig.update_layout(
        title="H-E-V-AC 风险结构雷达图",
        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
        showlegend=False,
        height=520,
        margin=dict(l=40, r=40, t=80, b=40),
        font=dict(family="Microsoft YaHei, SimHei, Arial, sans-serif", size=14)
    )
    return fig

def generate_diagnosis(result):
    H,E,V,AC,R,level = result["H 气候危险性"],result["E 暴露度"],result["V 脆弱性"],result["AC 适应力"],result["R 综合气候风险"],result["风险等级"]
    drivers=[]
    if H>=0.6: drivers.append("气候危险性较高，说明高温、强降水、连续降雨或冻融等外部气候压力较明显")
    if E>=0.6: drivers.append("暴露度较高，说明居民、游客、传统建筑和公共服务设施较为集中")
    if V>=0.6: drivers.append("脆弱性较高，说明传统建筑、排水条件、街巷空间或生态调节能力存在短板")
    if AC<0.5: drivers.append("适应力偏弱，说明排水改造、应急避难、预警响应或修缮维护能力仍需提升")
    if not drivers: drivers.append("各风险成分整体处于中低水平，但仍需结合历史事件进行校验")
    suggestions=["加强连续降雨和强降水条件下的传统建筑巡查与修缮维护","完善古城排水系统、易涝点治理和雨洪调蓄能力","优化节假日游客高峰期疏散、预警发布和公共服务保障","结合老年居民和游客暴露特征，完善高温热浪和低温冻融应急响应"]
    return f"""平遥古城及周边人居空间综合气候风险指数为 **{R:.3f}**，风险等级为 **{level}**。\n\n从风险结构看，气候危险性为 **{H:.3f}**，暴露度为 **{E:.3f}**，脆弱性为 **{V:.3f}**，适应力为 **{AC:.3f}**。\n\n**主要风险驱动因素：**\n""" + "\n".join([f"- {d}" for d in drivers]) + "\n\n**建议优先方向：**\n" + "\n".join([f"- {s}" for s in suggestions])

st.markdown('<div class="main-header"><h1>平遥古城气候风险量化评估平台 V1.2</h1><p>面向人居环境及基础设施的 H—E—V—AC 综合指数评估原型工具</p></div>', unsafe_allow_html=True)

st.sidebar.title("功能导航")
page = st.sidebar.radio("请选择功能页面", ["首页","数据导入与校验","气候危险性指标计算","风险成分赋值与权重","综合评价结果","数据导出"], index=0)
st.sidebar.markdown("---"); st.sidebar.subheader("综合风险权重")
wH = st.sidebar.number_input("H 气候危险性权重",0.0,1.0,0.35,0.01)
wE = st.sidebar.number_input("E 暴露度权重",0.0,1.0,0.25,0.01)
wV = st.sidebar.number_input("V 脆弱性权重",0.0,1.0,0.25,0.01)
wAC = st.sidebar.number_input("AC 适应力不足权重",0.0,1.0,0.15,0.01)
weight_sum = wH+wE+wV+wAC; st.sidebar.caption(f"当前权重合计：{weight_sum:.2f}")
if weight_sum>0 and abs(weight_sum-1)>0.001:
    st.sidebar.warning("权重合计不等于 1，已自动按比例归一化。")
    wH,wE,wV,wAC = wH/weight_sum,wE/weight_sum,wV/weight_sum,wAC/weight_sum

if page == "首页":
    st.markdown('<div class="warning-card"><b>数据安全提示：</b>公开演示版本仅用于方法展示，请勿上传涉密、内部或未公开数据。真实项目数据建议在本地环境或内部服务器运行。</div>', unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4); c1.metric("研究对象","平遥古城"); c2.metric("评价框架","H-E-V-AC"); c3.metric("风险类型","5类"); c4.metric("输出成果","指数+图表+Excel")
    st.markdown("### 平台定位")
    st.write("本平台用于演示平遥古城及周边人居空间在气候变化背景下的风险评估流程。第一版重点实现数据导入、气候指标计算、风险成分赋值、综合风险指数计算和结果导出。")
    st.markdown("### 评估流程")
    st.markdown("1. **数据导入与校验**：上传数据收集表或逐日气候数据，检查字段和缺失值。  \n2. **气候危险性指标计算**：计算高温、强降水、干旱、连续降雨和冻融指标。  \n3. **风险成分赋值与权重设置**：输入 H、E、V、AC 分值并设置权重。  \n4. **综合评价结果**：输出综合风险指数、风险等级、结构图和自动诊断结论。  \n5. **数据导出**：导出 Excel 结果，便于放入报告或后续复核。")
    st.info("当前 V1.2 仍属于原型工具。E、V、AC 仍采用 0—1 分值输入；后续可升级为自动读取 Excel 原始指标并标准化计算。")

elif page == "数据导入与校验":
    st.header("数据导入与校验"); st.write("上传 Excel 数据表后，平台可预览工作表内容。")
    uploaded_excel = st.file_uploader("上传平遥古城数据收集表 Excel", type=["xlsx"], key="excel_upload")
    if uploaded_excel is not None:
        try:
            excel_data = pd.read_excel(uploaded_excel, sheet_name=None); st.session_state["excel_data"] = excel_data
            st.success("Excel 上传成功"); st.write("识别到工作表：", list(excel_data.keys()))
            sheet = st.selectbox("选择工作表预览", list(excel_data.keys())); preview_df = excel_data[sheet]
            st.dataframe(preview_df, use_container_width=True)
            c1,c2,c3 = st.columns(3); c1.metric("工作表数量", len(excel_data)); c2.metric("当前表行数", preview_df.shape[0]); c3.metric("当前表列数", preview_df.shape[1])
        except Exception as e: st.error(f"读取 Excel 失败：{e}")
    else: st.info("如果只是测试平台，也可以先不上传 Excel，直接进入“风险成分赋值与权重”。")

elif page == "气候危险性指标计算":
    st.header("气候危险性指标计算"); st.write("上传逐日气候数据，至少需要包含：日期、最高气温、最低气温、降水量。")
    climate_file = st.file_uploader("上传逐日气候数据 CSV 或 Excel", type=["csv","xlsx"], key="climate_file")
    if climate_file is not None:
        try:
            climate_df = pd.read_csv(climate_file) if climate_file.name.lower().endswith(".csv") else pd.read_excel(climate_file)
            st.dataframe(climate_df.head(10), use_container_width=True)
            cols = climate_df.columns.tolist(); c1,c2,c3,c4 = st.columns(4)
            date_col = c1.selectbox("日期列", cols); tmax_col = c2.selectbox("最高气温列", cols); tmin_col = c3.selectbox("最低气温列", cols); pre_col = c4.selectbox("降水量列", cols)
            st.markdown("#### 数据完整性检查")
            check_df = pd.DataFrame({"字段":[date_col,tmax_col,tmin_col,pre_col],"缺失值数量":[climate_df[date_col].isna().sum(),pd.to_numeric(climate_df[tmax_col],errors="coerce").isna().sum(),pd.to_numeric(climate_df[tmin_col],errors="coerce").isna().sum(),pd.to_numeric(climate_df[pre_col],errors="coerce").isna().sum()]})
            st.dataframe(check_df, use_container_width=True)
            if st.button("计算气候危险性指标", type="primary"):
                climate_result, meta = calc_climate_indices(climate_df,date_col,tmax_col,tmin_col,pre_col)
                st.session_state["climate_result"] = climate_result; st.session_state["climate_meta"] = meta; st.success("气候指标计算完成")
            if "climate_result" in st.session_state:
                st.subheader("气候指标计算结果"); st.dataframe(st.session_state["climate_result"], use_container_width=True)
                meta = st.session_state.get("climate_meta", {})
                if meta:
                    c1,c2,c3 = st.columns(3); c1.metric("记录条数", meta.get("记录条数","-")); c2.metric("起始日期", str(meta.get("起始日期",""))[:10]); c3.metric("结束日期", str(meta.get("结束日期",""))[:10])
        except Exception as e: st.error(f"气候数据处理失败：{e}")
    else: st.info("请上传逐日气候数据。若暂时没有数据，可先进入“风险成分赋值与权重”手动设置 H 值。")

elif page == "风险成分赋值与权重":
    st.header("风险成分赋值与权重设置"); st.info("单个案例 V1.2 暂采用 0—1 分值输入。0 表示最低，1 表示最高。")
    col_left,col_right = st.columns([2,1])
    with col_left:
        st.subheader("H 气候危险性")
        H_heat=st.slider("高温热浪危险性",0.0,1.0,0.60,0.01); H_flood=st.slider("暴雨洪涝危险性",0.0,1.0,0.70,0.01); H_rain=st.slider("连续降雨危险性",0.0,1.0,0.65,0.01); H_drought=st.slider("干旱缺水危险性",0.0,1.0,0.45,0.01); H_freeze=st.slider("低温冻融危险性",0.0,1.0,0.50,0.01)
        H=float(np.mean([H_heat,H_flood,H_rain,H_drought,H_freeze]))
        st.subheader("E 暴露度")
        E_population=st.slider("人口与游客暴露",0.0,1.0,0.70,0.01); E_building=st.slider("传统建筑与老旧建筑暴露",0.0,1.0,0.80,0.01); E_infra=st.slider("道路与基础设施暴露",0.0,1.0,0.60,0.01); E_service=st.slider("公共服务设施暴露",0.0,1.0,0.55,0.01)
        E=float(np.mean([E_population,E_building,E_infra,E_service]))
        st.subheader("V 脆弱性")
        V_building=st.slider("建筑脆弱性",0.0,1.0,0.80,0.01); V_drainage=st.slider("排水脆弱性",0.0,1.0,0.70,0.01); V_social=st.slider("社会脆弱性",0.0,1.0,0.55,0.01); V_ecology=st.slider("生态调节脆弱性",0.0,1.0,0.60,0.01); V_traffic=st.slider("交通与消防通道脆弱性",0.0,1.0,0.65,0.01)
        V=float(np.mean([V_building,V_drainage,V_social,V_ecology,V_traffic]))
        st.subheader("AC 适应力")
        AC_engineering=st.slider("工程适应力",0.0,1.0,0.45,0.01); AC_ecology=st.slider("生态适应力",0.0,1.0,0.40,0.01); AC_emergency=st.slider("应急适应力",0.0,1.0,0.55,0.01); AC_service=st.slider("公共服务适应力",0.0,1.0,0.50,0.01); AC_governance=st.slider("治理适应力",0.0,1.0,0.60,0.01)
        AC=float(np.mean([AC_engineering,AC_ecology,AC_emergency,AC_service,AC_governance]))
    R=float(wH*H+wE*E+wV*V+wAC*(1-AC)); level=risk_level(R)
    st.session_state["risk_result"] = {"H 气候危险性":H,"E 暴露度":E,"V 脆弱性":V,"AC 适应力":AC,"1-AC 适应能力不足":1-AC,"R 综合气候风险":R,"风险等级":level}
    subrisk = pd.DataFrame({"风险类型":["高温热浪风险","暴雨洪涝风险","连续降雨建筑潮湿风险","干旱缺水风险","低温冻融风险"],"危险性分值":[H_heat,H_flood,H_rain,H_drought,H_freeze]})
    subrisk["风险指数_示范"] = [wH*x+wE*E+wV*V+wAC*(1-AC) for x in subrisk["危险性分值"]]
    subrisk["风险等级"] = subrisk["风险指数_示范"].apply(risk_level); st.session_state["subrisk_result"] = subrisk
    with col_right:
        st.subheader("即时计算结果"); st.metric("综合风险指数 R", f"{R:.3f}"); show_risk_badge(level); st.caption("计算公式：R = wH×H + wE×E + wV×V + wAC×(1-AC)"); st.dataframe(pd.DataFrame({"维度":["H","E","V","1-AC"],"权重":[wH,wE,wV,wAC]}), use_container_width=True)

elif page == "综合评价结果":
    st.header("综合评价结果")
    if "risk_result" not in st.session_state: st.info("请先进入“风险成分赋值与权重”页面完成计算。")
    else:
        result=st.session_state["risk_result"]; result_df=pd.DataFrame({"项目":list(result.keys()),"结果":list(result.values())}); subrisk_df=st.session_state.get("subrisk_result")
        c1,c2,c3,c4,c5=st.columns(5); c1.metric("H 气候危险性",f"{result['H 气候危险性']:.3f}"); c2.metric("E 暴露度",f"{result['E 暴露度']:.3f}"); c3.metric("V 脆弱性",f"{result['V 脆弱性']:.3f}"); c4.metric("AC 适应力",f"{result['AC 适应力']:.3f}"); c5.metric("R 综合风险",f"{result['R 综合气候风险']:.3f}")
        show_risk_badge(result["风险等级"]); st.subheader("结果表"); st.dataframe(result_df, use_container_width=True)
        st.subheader("风险结构图"); chart_df=pd.DataFrame({"维度":["H 气候危险性","E 暴露度","V 脆弱性","1-AC 适应能力不足"],"指数值":[result["H 气候危险性"],result["E 暴露度"],result["V 脆弱性"],result["1-AC 适应能力不足"]]})
        g1,g2=st.columns(2); g1.pyplot(plot_bar(chart_df)); g2.pyplot(plot_radar(chart_df["维度"], chart_df["指数值"]))
        if subrisk_df is not None:
            st.subheader("单灾种风险示范结果"); st.dataframe(subrisk_df, use_container_width=True)
            fig,ax=plt.subplots(figsize=(8,4.6)); ax.bar(subrisk_df["风险类型"],subrisk_df["风险指数_示范"]); ax.set_ylim(0,1); ax.set_ylabel("风险指数"); ax.set_title("单灾种风险指数示范"); plt.xticks(rotation=20, ha="right"); plt.tight_layout(); st.pyplot(fig)
        st.subheader("自动诊断结论"); st.markdown(generate_diagnosis(result))

elif page == "数据导出":
    st.header("数据导出")
    if "risk_result" not in st.session_state: st.info("请先完成风险计算，再导出结果。")
    else:
        result=st.session_state["risk_result"]; result_df=pd.DataFrame({"项目":list(result.keys()),"结果":list(result.values())}); climate_df=st.session_state.get("climate_result"); subrisk_df=st.session_state.get("subrisk_result")
        output=make_result_excel(result_df,climate_df,subrisk_df)
        st.download_button(label="下载风险计算结果 Excel", data=output, file_name="平遥古城气候风险计算结果_V1.2.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.subheader("可复制文字结论"); st.markdown(generate_diagnosis(result))
