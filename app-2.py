import streamlit as st
from openai import OpenAI
import pandas as pd
import io
import re

st.set_page_config(page_title="出海游戏测试专家 Agent", page_icon="🎮", layout="wide")
st.title("🎮 出海游戏测试专家 Agent (SDET)")
st.caption("基于黑盒测试理论与出海专项策略，辅助生成测试方案与用例。")

with st.sidebar:
    st.header("🔐 配置中心")
    api_key = st.text_input("请输入 DeepSeek API Key", type="password")
    
    st.markdown("---")
    st.header("⚙️ 输出模式")
    output_mode = st.radio(
        "请选择输出格式：",
        ("完整方案（需求分析+专项策略+测试用例）", "只要测试用例（纯CSV）")
    )

# 基础 System Prompt（你的原版核心内容）
BASE_SYSTEM_PROMPT = """
# Role
你是一名拥有5年+出海游戏测试经验的测试专家（SDET），熟悉移动/PC/主机，SLG/卡牌/MMO/休闲，Google Play/App Store/第三方支付，GDPR/COPPA，弱网、本地化、跨天重置、支付回调、兼容性测试。

# Mission
根据用户提供的游戏策划案，输出专业、可落地的测试方案与测试用例。
如果策划案缺失、矛盾或不完整：先输出《待确认问题》和《显式假设》，不得编造关键规则。最多追问5个阻塞性问题；用户要求继续时，基于假设继续并标注风险。

# Workflow
## Step 1 需求分析与风险 (用 Markdown 表格输出)
需求ID | 模块 | 规则摘要 | 风险等级 | 测试类型 | 不测范围 | 待确认

## Step 2 专项测试策略 (用 Markdown 表格输出)
专项 | 测试场景 | 关键参数/数据 | 判定标准 | 优先级

## Step 3 详细测试用例 (纯 CSV 输出)
列名必须包含：用例编号,需求ID,测试模块,用例类型,设计方法,前置条件,测试数据,测试步骤,预期结果,优先级,执行端,是否自动化,备注
要求：必须使用等价类划分、边界值分析、场景法、错误推测法，并在“设计方法”列标注。
优先级定义：P0(阻塞/崩溃/资损)、P1(重要回归/异常)、P2(边缘/长尾)。
步骤可执行，预期结果可观测。
必须覆盖正例、反例、异常、并发、中断、幂等、恢复。
CSV 使用 RFC 4180 标准。
"""

# 根据 UI 选择动态拼装 Prompt
if output_mode == "只要测试用例（纯CSV）":
    SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """
# Output Format (IMPORTANT)
用户只要用例。请跳过 Step 1 和 Step 2，**只输出 Step 3 的纯 CSV 文本**。
必须在 CSV 文本的前后分别加上独特的分隔符，格式严格如下：
===CSV_START===
(这里放纯CSV数据，不加任何Markdown标记)
===CSV_END===
如果用例过多需要分批，请输出多组上述分隔符包裹的 CSV 数据。
"""
else:
    SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """
# Output Format (IMPORTANT)
用户要求完整方案。
Step 1 和 Step 2 必须使用 Markdown 表格。
Step 3 必须输出纯 CSV，不要加 ```csv 标记。
为了便于代码解析，**Step 3 的 CSV 数据前后必须加上独特的分隔符**，格式严格如下：
===CSV_START===
(这里放纯CSV数据)
===CSV_END===
"""

st.subheader("📝 输入游戏策划案")
requirement = st.text_area(
    "请尽可能详细地输入策划案（包含游戏类型、平台、目标地区、核心模块、数值规则等）",
    height=200
)

if st.button("🚀 开始生成", type="primary"):
    if not api_key:
        st.error("请先在左侧配置 API Key！")
    elif not requirement:
        st.warning("请输入游戏策划案！")
    else:
        with st.spinner("Agent 正在拆解需求、推导专项策略并生成用例..."):
            try:
                client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"请为以下游戏策划案输出测试方案与用例：\n{requirement}"}
                    ],
                    temperature=0.2,
                )
                
                result = response.choices[0].message.content
                st.success("✅ 生成完毕！")
                
                # ================= 核心解析引擎 =================
                
                # 提取所有的 CSV 块
                # 使用正则表达式匹配 ===CSV_START=== 和 ===CSV_END=== 之间的内容
                csv_blocks = re.findall(r'===CSV_START===\s*(.*?)\s*===CSV_END===', result, re.DOTALL)
                
                # 提取并展示 Markdown 部分 (Step 1 和 Step 2)
                markdown_part = re.split(r'===CSV_START===', result)[0].strip()
                if markdown_part:
                    st.markdown("### 📋 需求分析与专项测试策略")
                    st.markdown(markdown_part)
                
                if not csv_blocks:
                    st.warning("⚠️ 未检测到符合规范的 CSV 数据块，可能是 AI 格式输出异常。下面是原始输出：")
                    st.text_area("原始输出内容", result, height=300)
                else:
                    st.markdown("### 📊 详细测试用例")
                    all_dfs = []
                    
                    for idx, csv_data in enumerate(csv_blocks):
                        # 清理可能残留的 Markdown 代码块标记
                        cleaned_csv = re.sub(r'^```csv\s*', '', csv_data.strip())
                        cleaned_csv = re.sub(r'```$', '', cleaned_csv.strip())
                        
                        if cleaned_csv:
                            try:
                                df = pd.read_csv(io.StringIO(cleaned_csv))
                                all_dfs.append(df)
                                st.markdown(f"**第 {idx+1} 批用例**")
                                st.dataframe(df, use_container_width=True)
                            except Exception as e:
                                st.error(f"解析第 {idx+1} 批 CSV 失败：{e}")
                                st.text(cleaned_csv)
                    
                    # 合并导出
                    if all_dfs:
                        final_df = pd.concat(all_dfs, ignore_index=True)
                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                            final_df.to_excel(writer, index=False, sheet_name='测试用例')
                        
                        st.download_button(
                            label="📥 下载完整 Excel 用例",
                            data=buffer.getvalue(),
                            file_name="出海游戏测试用例.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                # ================= 解析引擎结束 =================
                
            except Exception as e:
                st.error(f"发生错误：{e}")