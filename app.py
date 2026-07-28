from __future__ import annotations

import io
import hmac
import os
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

# This must remain the first Streamlit command. Reading st.secrets also counts
# as a Streamlit command on the installed Streamlit version.
st.set_page_config(page_title="我的记账本", page_icon="💰", layout="wide")

try:
    database_url = str(st.secrets.get("database_url", ""))
except Exception:
    database_url = ""
if database_url:
    os.environ["DATABASE_URL"] = database_url

import database as db


def require_login() -> None:
    """Show a password gate when app_password is configured in Secrets."""
    try:
        configured_password = str(st.secrets.get("app_password", ""))
    except Exception:
        configured_password = ""

    # No secret keeps the existing local-development experience unchanged.
    if not configured_password or st.session_state.get("authenticated"):
        return

    st.title("🔒 轻账本")
    st.caption("请输入访问密码")
    password = st.text_input("访问密码", type="password", key="login_password")
    if st.button("进入账本", type="primary", use_container_width=True):
        if hmac.compare_digest(password, configured_password):
            st.session_state["authenticated"] = True
            st.session_state.pop("login_password", None)
            st.rerun()
        st.error("密码不正确，请重试。")
    st.stop()


require_login()
db.init_db()


PAGES = {"home": "📊 首页概览", "bills": "📑 账单列表", "accounts": "💳 账户管理", "stats": "📈 统计分析"}
st.session_state.setdefault("page", PAGES["home"])
st.session_state.setdefault("mobile_add_screen", False)
st.session_state.setdefault("sidebar_navigation", st.session_state["page"])


def navigate_to(page: str, add_screen: bool = False) -> None:
    """Navigate without replacing the Streamlit browser session or login state."""
    st.session_state["page"] = page
    st.session_state["sidebar_navigation"] = page
    st.session_state["mobile_add_screen"] = add_screen


MOBILE_NAV_COMPONENT = None
if hasattr(st.components, "v2"):
    MOBILE_NAV_COMPONENT = st.components.v2.component(
        "account_book_mobile_navigation",
        html="""
        <nav class="tabbar" aria-label="底部导航">
          <button data-tab="home"><span>▤</span><b>账本</b></button>
          <button data-tab="bills"><span>≡</span><b>账单</b></button>
          <button data-tab="add" class="add"><span>＋</span><b>记账</b></button>
          <button data-tab="stats"><span>▥</span><b>统计</b></button>
          <button data-tab="accounts"><span>●</span><b>我的</b></button>
        </nav>
        """,
        css="""
        .tabbar { box-sizing:border-box; position:fixed; z-index:1000; left:8px; right:8px; bottom:calc(8px + env(safe-area-inset-bottom)); display:flex; align-items:center; gap:4px; width:auto; height:72px; padding:8px 10px; background:rgba(255,253,249,.98); border:1px solid #eee4dc; border-radius:24px 24px 34px 34px; box-shadow:0 8px 28px rgba(62,45,35,.16); font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
        button { flex:1; min-width:0; height:52px; border:0; border-radius:16px; background:transparent; color:#84766d; cursor:pointer; font:inherit; font-size:11px; line-height:1.25; }
        button span, button b { display:block; } button span { font-size:22px; line-height:24px; font-weight:500; } button b { margin-top:2px; font-weight:600; white-space:nowrap; }
        button.active { background:#d8f5ed; color:#127d70; } button.add span { font-size:27px; line-height:22px; }
        button:active { transform:scale(.96); }
        @media (min-width:900px) { .tabbar { left:50%; right:auto; bottom:52px; width:370px; transform:translateX(-50%); } }
        """,
        js="""
        export default function(component) {
          const { data, parentElement, setTriggerValue } = component
          const root = parentElement || document
          root.querySelectorAll("button").forEach((button) => {
            button.classList.toggle("active", button.dataset.tab === (data?.active || "home"))
            button.onclick = () => setTriggerValue("navigate", button.dataset.tab)
          })
        }
        """,
    )


def handle_mobile_navigation() -> None:
    payload = st.session_state.get("mobile_navigation", {})
    tab = payload.get("navigate") if isinstance(payload, dict) else None
    target = {"home": (PAGES["home"], False), "bills": (PAGES["bills"], False), "add": (PAGES["home"], True), "stats": (PAGES["stats"], False), "accounts": (PAGES["accounts"], False)}.get(tab)
    if target:
        navigate_to(*target)

st.markdown(
    """
    <style>
    .block-container { max-width: 1180px; padding-top: 2rem; }
    .mobile-shell { max-width: 430px; margin: 0 auto; background: #fff8f1; border: 1px solid #f1dfd2; border-radius: 28px; padding: 18px 16px 24px; box-shadow: 0 12px 34px rgba(142,91,54,.12); }
    .mobile-hero { background: linear-gradient(135deg,#ffd8b0,#ffe9d7); border-radius: 22px; padding: 20px; color: #714a34; margin-bottom: 14px; }
    .mobile-title { font-size: 23px; font-weight: 750; margin-bottom: 5px; }
    .mobile-subtitle { font-size: 13px; color: #9b7258; }
    .mobile-card { background: white; border-radius: 18px; padding: 16px; margin: 10px 0; border: 1px solid #f6e9df; }
    .mobile-section { font-weight: 700; color: #694736; margin: 18px 2px 8px; }
    .mobile-category { display: inline-block; width: 23%; margin: 1%; padding: 12px 4px; background: white; border-radius: 16px; text-align: center; font-size: 12px; color: #684938; border: 1px solid #f5e5d9; }
    .mobile-amount { font-size: 28px; font-weight: 800; color: #51382b; }
    .mobile-nav { display: flex; justify-content: space-around; color: #9a6d52; font-size: 12px; padding-top: 12px; border-top: 1px solid #f0dfd4; margin-top: 18px; }
    .mobile-install-tip { color: #9b7258; font-size: 12px; text-align: center; margin: 18px 4px 8px; }
    /* Fixed mobile tab bar. Each native Streamlit button gets a dedicated slot. */
    .mobile-bottom-nav-anchor, .bottom-tab-slot { display: none; }
    body:has(.bottom-tab-slot)::before {
      content: ""; position: fixed; z-index: 990; left: 0; right: 0; bottom: 0;
      height: calc(70px + env(safe-area-inset-bottom));
      background: rgba(255,253,249,.97); border-top: 1px solid #eee5de;
      box-shadow: 0 -8px 28px rgba(60,45,35,.10); backdrop-filter: blur(18px);
      pointer-events: none;
    }
    [data-testid="column"]:has(.bottom-tab-slot) {
      position: fixed !important; z-index: 991 !important; bottom: calc(8px + env(safe-area-inset-bottom));
      width: 20% !important; min-width: 0 !important; padding: 0 4px !important;
    }
    [data-testid="column"]:has(.tab-slot-0) { left: 0; }
    [data-testid="column"]:has(.tab-slot-1) { left: 20%; }
    [data-testid="column"]:has(.tab-slot-2) { left: 40%; }
    [data-testid="column"]:has(.tab-slot-3) { left: 60%; }
    [data-testid="column"]:has(.tab-slot-4) { left: 80%; }
    [data-testid="column"]:has(.bottom-tab-slot) .stButton button {
      width: 100%; min-height: 52px; padding: 2px 0; border: 0; background: transparent;
      color: #84766d; font-size: 11px; line-height: 1.35; box-shadow: none; border-radius: 18px;
    }
    [data-testid="column"]:has(.bottom-tab-slot) .stButton button[kind="primary"] {
      background: #d8f5ed; color: #127d70; font-weight: 700; border-radius: 18px;
    }
    [data-testid="column"]:has(.bottom-tab-slot) .stButton button:hover { color: #127d70; background: #eefaf6; }

    /* iPhone Safari: full-width canvas, Dynamic Island and home-indicator safe areas. */
    @media (max-width: 899px) {
      .stApp { background: #fff8f1; }
      [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none !important; }
      .main .block-container {
        max-width: none !important; min-height: 100dvh;
        margin: 0 !important;
        padding: max(24px, env(safe-area-inset-top)) 16px calc(92px + env(safe-area-inset-bottom)) !important;
      }
      .mobile-shell { max-width: none; margin: 0; padding: 0; border: 0; border-radius: 0; box-shadow: none; background: transparent; }
      .mobile-hero { border-radius: 22px; padding: 18px; }
      .mobile-card { border-radius: 17px; }
      .stButton > button { min-height: 44px; }
      [data-testid="stForm"] { border-radius: 20px; padding: 16px 14px; background: #fffdf9; }
    }

    /* Desktop preview: an interactive iPhone 16 Pro-sized canvas (402 × 874 CSS px). */
    @media (min-width: 900px) {
      .stApp { background: radial-gradient(circle at 52% 20%, #fff7ed 0%, #f3eee9 42%, #e8e9ed 100%); }
      .main .block-container {
        width: 402px !important;
        max-width: 402px !important;
        min-height: 874px;
        margin: 30px auto 44px !important;
        padding: 62px 16px 32px !important;
        background: #fff8f1;
        border: 8px solid #1c1c1e;
        border-radius: 54px;
        box-shadow: 0 26px 72px rgba(29, 25, 20, .34), inset 0 0 0 1px rgba(255,255,255,.18);
        position: relative;
        overflow: hidden;
      }
      .main .block-container::before {
        content: "";
        position: absolute;
        z-index: 10;
        top: 14px;
        left: 50%;
        width: 126px;
        height: 34px;
        transform: translateX(-50%);
        border-radius: 22px;
        background: #070707;
        box-shadow: 0 1px 1px rgba(255,255,255,.12);
      }
      .main .block-container::after {
        content: "iPhone 16 Pro · 轻账本";
        position: fixed;
        bottom: 18px;
        left: calc(50% + 135px);
        color: #8c8278;
        font-size: 12px;
        letter-spacing: .08em;
      }
      .mobile-shell {
        max-width: none;
        margin: 0;
        padding: 0;
        border: 0;
        border-radius: 0;
        background: transparent;
        box-shadow: none;
      }
      [data-testid="stSidebar"] { border-right: 1px solid #e8ddd3; }
      [data-testid="stToolbar"] { visibility: hidden; }
      body:has(.bottom-tab-slot)::before { left: calc(50% - 185px); right: auto; bottom: 52px; width: 370px; height: 70px; border-radius: 22px 22px 42px 42px; }
      [data-testid="column"]:has(.bottom-tab-slot) { bottom: 60px; width: 74px !important; }
      [data-testid="column"]:has(.tab-slot-0) { left: calc(50% - 185px); }
      [data-testid="column"]:has(.tab-slot-1) { left: calc(50% - 111px); }
      [data-testid="column"]:has(.tab-slot-2) { left: calc(50% - 37px); }
      [data-testid="column"]:has(.tab-slot-3) { left: calc(50% + 37px); }
      [data-testid="column"]:has(.tab-slot-4) { left: calc(50% + 111px); }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def money(cents: int) -> str:
    return f"¥{cents / 100:,.2f}"


def account_map() -> dict[str, dict]:
    return {row["name"]: row for row in db.accounts()}


def add_transaction_form(form_key: str = "add_tx"):
    with st.form(form_key, clear_on_submit=True):
        kind = st.radio("类型", ["支出", "收入"], horizontal=True, key=f"{form_key}_kind")
        type_id = 1 if kind == "支出" else 2
        category_options = db.EXPENSE_CATEGORIES if type_id == 1 else db.INCOME_CATEGORIES
        preferred = st.session_state.get("quick_category")
        category_index = category_options.index(preferred) if preferred in category_options else 0
        category = st.selectbox("分类", category_options, index=category_index, key=f"{form_key}_category")
        accounts = account_map()
        account_name = st.selectbox("账户", list(accounts), key=f"{form_key}_account")
        amount = st.number_input("金额（元）", min_value=0.01, step=1.0, format="%.2f", key=f"{form_key}_amount")
        note = st.text_input("备注", placeholder="例如：午餐、地铁、工资", key=f"{form_key}_note")
        tx_date = st.date_input("日期", date.today(), key=f"{form_key}_date")
        if st.form_submit_button("保存这笔账", type="primary", use_container_width=True):
            db.add_transaction(accounts[account_name]["id"], type_id, round(amount * 100), category, note, tx_date)
            st.success("已记录")
            st.rerun()


def overview():
    today = date.today()
    first = today.replace(day=1)
    rows = db.query_transactions(first.isoformat(), today.isoformat())
    income = sum(row["amount_cents"] for row in rows if row["type"] == 2)
    expense = sum(row["amount_cents"] for row in rows if row["type"] == 1)
    balance = sum(row["balance_cents"] for row in db.account_balances())

    is_add_screen = st.session_state.get("mobile_add_screen", False)
    st.markdown('<div class="mobile-shell">', unsafe_allow_html=True)
    if is_add_screen:
        st.markdown('<div class="mobile-hero"><div class="mobile-title">记一笔</div><div class="mobile-subtitle">随时记录，让每一笔都清楚</div></div>', unsafe_allow_html=True)
        add_transaction_form("full_screen_add")
        st.markdown('</div>', unsafe_allow_html=True)
        return
    st.markdown(f'<div class="mobile-hero"><div class="mobile-title">我的记账本</div><div class="mobile-subtitle">记录每一笔，让生活更有数 · {today:%Y年%m月}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="mobile-card"><div style="color:#a47a60;font-size:13px">当前结余</div><div class="mobile-amount">{money(balance)}</div><div style="color:#b28a73;font-size:12px">本月收入 {money(income)}　·　支出 {money(expense)}</div></div>', unsafe_allow_html=True)
    icons = [("🍜", "餐饮", "餐饮美食"), ("🛍️", "购物", "购物消费"), ("🏠", "居家", "居家生活"), ("🚇", "交通", "交通出行"), ("🎮", "娱乐", "休闲娱乐"), ("💊", "医疗", "医疗健康"), ("📚", "学习", "教育学习"), ("➕", "更多", None)]
    st.markdown('<div class="mobile-section">快捷分类</div>', unsafe_allow_html=True)
    category_cols = st.columns(4)
    for index, (icon, name, category_name) in enumerate(icons):
        if category_cols[index % 4].button(f"{icon}\n{name}", key=f"quick_category_{index}", use_container_width=True):
            if category_name:
                st.session_state["quick_category"] = category_name
                st.session_state["mobile_add_category"] = category_name
            st.session_state["page"] = "📊 首页概览"
            st.rerun()
    st.markdown('<div class="mobile-section">添加一笔</div>', unsafe_allow_html=True)
    add_transaction_form("mobile_add")
    st.markdown('<div class="mobile-section">最近记录</div>', unsafe_allow_html=True)
    latest = db.query_transactions()[:5]
    if latest:
        for row in latest:
            sign = "+" if row["type"] == 2 else "-"
            color = "#48a27a" if row["type"] == 2 else "#e87965"
            st.markdown(f'<div class="mobile-card" style="padding:11px 14px;display:flex;justify-content:space-between"><span>🧾 {row["category"]}<br><small style="color:#aa8976">{row["transaction_date"]} · {row["account_name"]}</small></span><b style="color:{color}">{sign}{money(row["amount_cents"])}</b></div>', unsafe_allow_html=True)
    else:
        st.info("还没有记录，先记下第一笔吧")
    st.markdown('<div class="mobile-install-tip">iPhone 上请使用 Safari：分享 → 添加到主屏幕，即可像 App 一样快速打开。</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


def bills():
    st.title("📑 账单列表")
    c1, c2, c3 = st.columns(3)
    start = c1.date_input("开始日期", date.today().replace(day=1), key="filter_start")
    end = c2.date_input("结束日期", date.today(), key="filter_end")
    accounts = account_map()
    account_name = c3.selectbox("账户", ["全部账户"] + list(accounts), key="filter_account")
    category = st.selectbox("分类", ["全部分类"] + db.EXPENSE_CATEGORIES + db.INCOME_CATEGORIES, key="filter_category")
    rows = db.query_transactions(start.isoformat(), end.isoformat(), accounts[account_name]["id"] if account_name != "全部账户" else None, category if category != "全部分类" else None)
    st.caption(f"共 {len(rows)} 条记录")
    for row in rows:
        cols = st.columns([1.1, 1.2, 1.2, 1, 1.4, .5])
        cols[0].write(row["transaction_date"])
        cols[1].write("收入" if row["type"] == 2 else "支出")
        cols[2].write(row["category"])
        cols[3].write(row["account_name"])
        cols[4].write(("+" if row["type"] == 2 else "-") + money(row["amount_cents"]))
        if cols[5].button("删除", key=f"del_{row['id']}"):
            db.delete_transaction(row["id"])
            st.rerun()
        if row["note"]:
            st.caption(f"　└ {row['note']}")


def accounts_page():
    st.title("💳 账户管理")
    for row in db.account_balances():
        c1, c2, c3 = st.columns([1.5, 2, .7])
        c1.write(f"### {row['icon']} {row['name']}")
        c2.write(f"余额：**{money(row['balance_cents'])}**")
        if c3.button("删除", key=f"account_del_{row['id']}"):
            try:
                db.delete_account(row["id"])
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    st.divider()
    st.subheader("新增账户")
    with st.form("new_account"):
        c1, c2, c3, c4 = st.columns(4)
        name = c1.text_input("名称")
        kind_choice = c2.selectbox("类型", ["现金", "银行卡", "微信", "支付宝", "自定义类型"])
        opening = c3.number_input("初始余额（元）", min_value=0.0, step=100.0)
        icon = c4.text_input("自定义图标", "💰")
        custom_kind = st.text_input("自定义账户类型", placeholder="例如：信用卡、储蓄卡、公司账户") if kind_choice == "自定义类型" else ""
        if st.form_submit_button("添加", type="primary"):
            try:
                kind = {"现金": "cash", "银行卡": "bank", "微信": "wechat", "支付宝": "alipay"}.get(kind_choice, custom_kind.strip() or "custom")
                db.add_account(name, kind, round(opening * 100), icon)
                st.rerun()
            except Exception as exc:
                st.error(f"添加失败：{exc}")
    st.subheader("账户间转账")
    with st.form("transfer"):
        accounts = account_map()
        names = list(accounts)
        c1, c2, c3, c4 = st.columns(4)
        source_name = c1.selectbox("转出", names)
        target_name = c2.selectbox("转入", names)
        amount = c3.number_input("金额（元）", min_value=0.01, step=1.0)
        fee = c4.number_input("手续费（元）", min_value=0.0, step=.5)
        note = st.text_input("备注", key="transfer_note")
        if st.form_submit_button("确认转账"):
            try:
                db.add_transfer(accounts[source_name]["id"], accounts[target_name]["id"], round(amount * 100), round(fee * 100), note, date.today())
                st.success("转账成功")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def stats():
    st.title("📈 统计分析")
    rows = db.query_transactions((date.today() - timedelta(days=180)).isoformat(), date.today().isoformat())
    if not rows:
        st.info("暂无数据可供分析")
        return
    frame = pd.DataFrame([dict(row) for row in rows])
    frame["金额"] = frame["amount_cents"].abs() / 100
    frame["交易日期"] = pd.to_datetime(frame["transaction_date"], errors="coerce")
    frame = frame.dropna(subset=["交易日期"])
    frame["月份"] = frame["交易日期"].dt.to_period("M").dt.to_timestamp()
    left, right = st.columns(2)
    expense = frame[frame.type == 1]
    if not expense.empty:
        left.plotly_chart(px.pie(expense, values="金额", names="category", title="支出分类占比"), use_container_width=True)
    trend = frame.groupby(["月份", "type"], as_index=False)["金额"].sum().sort_values("月份")
    trend["类型"] = trend.type.map({1: "支出", 2: "收入"})
    trend_fig = px.line(trend, x="月份", y="金额", color="类型", markers=True, title="近半年收支趋势")
    trend_fig.update_xaxes(tickformat="%Y-%m", dtick="M1", title="月份")
    trend_fig.update_yaxes(tickformat=".2f", title="金额（元）")
    right.plotly_chart(trend_fig, use_container_width=True)
    st.subheader("支出排行")
    st.dataframe(expense.groupby("category")["金额"].sum().sort_values(ascending=False).rename("金额（元）").to_frame(), use_container_width=True)


def settings():
    st.title("⚙️ 数据设置")
    st.write("数据库文件：", db.DB_PATH)
    rows = db.query_transactions()
    if rows:
        data = pd.DataFrame([dict(row) for row in rows])
        data["金额（元）"] = data.pop("amount_cents") / 100
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            data.to_excel(writer, index=False, sheet_name="账单")
        st.download_button("下载 Excel 备份", output.getvalue(), "account_book_backup.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.subheader("CSV 导入")
    st.caption("CSV 需要包含：日期、金额、类型、分类、账户、备注。")
    uploaded = st.file_uploader("选择 CSV 文件", type=["csv"])
    if uploaded:
        try:
            raw = pd.read_csv(uploaded, encoding="utf-8-sig")
            st.dataframe(raw.head(), use_container_width=True)
            if st.button("导入这些记录", type="primary"):
                accounts = account_map()
                imported = []
                for _, row in raw.iterrows():
                    account = accounts[str(row["账户"])]
                    type_id = 2 if str(row["类型"]) == "收入" else 1
                    imported.append((account["id"], type_id, round(float(row["金额"]) * 100), str(row["分类"]), str(row.get("备注", "")), str(row["日期"])[:10], "import", account["id"], type_id, round(float(row["金额"]) * 100), str(row.get("备注", "")), str(row["日期"])[:10]))
                st.success(f"成功导入 {db.add_imported_transactions(imported)} 条记录")
                st.rerun()
        except Exception as exc:
            st.error(f"导入失败：{exc}")


pages = {"📊 首页概览": overview, "📑 账单列表": bills, "💳 账户管理": accounts_page, "📈 统计分析": stats, "⚙️ 设置": settings}
page_names = list(pages)
default_page = st.session_state.get("page", page_names[0])
if default_page not in page_names:
    default_page = page_names[0]
if st.session_state.get("sidebar_navigation") not in page_names:
    st.session_state["sidebar_navigation"] = default_page
choice = st.sidebar.radio("导航", page_names, index=page_names.index(default_page), key="sidebar_navigation")
st.session_state["page"] = choice
if choice != PAGES["home"]:
    st.session_state["mobile_add_screen"] = False
pages[choice]()

active_tab = 2 if st.session_state.get("mobile_add_screen") else {PAGES["home"]: 0, PAGES["bills"]: 1, PAGES["stats"]: 3, PAGES["accounts"]: 4}.get(choice, 0)
active_name = ["home", "bills", "add", "stats", "accounts"][active_tab]
if MOBILE_NAV_COMPONENT:
    MOBILE_NAV_COMPONENT(key="mobile_navigation", data={"active": active_name}, on_navigate_change=handle_mobile_navigation, height=72)
else:
    st.warning("当前本地 Streamlit 版本较旧；线上版本会显示五按钮底部导航。")
