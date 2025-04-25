import pandas as pd
import re
import requests
import json
import os
import streamlit as st
from requests.auth import HTTPBasicAuth

CONFIG_FILE = "jira_config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_config(email, api_token, project):
    with open(CONFIG_FILE, 'w') as f:
        json.dump({"email": email, "api_token": api_token, "project": project}, f)

def parse_estimate_to_minutes(value):
    try:
        seconds = float(value)
        return int(seconds / 60)
    except:
        days = hours = minutes = 0
        day_match = re.search(r"(\d+)d", str(value))
        hour_match = re.search(r"(\d+)h", str(value))
        minute_match = re.search(r"(\d+)m", str(value))

        if day_match:
            days = int(day_match.group(1))
        if hour_match:
            hours = int(hour_match.group(1))
        if minute_match:
            minutes = int(minute_match.group(1))

        return (days * 8 + hours) * 60 + minutes

def minutes_to_dhm(minutes):
    days = minutes // (8 * 60)
    hours = (minutes % (8 * 60)) // 60
    mins = minutes % 60
    return f"{days}d {hours}h {mins}m"

def fetch_issues_from_jira(jira_url, jql, email, api_token):
    headers = {
        "Accept": "application/json"
    }
    auth = HTTPBasicAuth(email, api_token)
    params = {
        "jql": jql,
        "fields": "summary,parent,timetracking"
    }

    response = requests.get(
        f"{jira_url}/rest/api/2/search",
        headers=headers,
        params=params,
        auth=auth
    )

    if response.status_code != 200:
        st.error(f"Jira API 요청 실패: {response.status_code} {response.text}")
        return []

    return response.json().get("issues", [])

def summarize_issues_from_api(jira_url, jql, email, api_token):
    issues = fetch_issues_from_jira(jira_url, jql, email, api_token)
    data = []

    for issue in issues:
        summary = issue['fields']['summary']
        estimate = issue['fields'].get('timetracking', {}).get('originalEstimateSeconds', 0)
        minutes = int(estimate / 60) if estimate else 0
        parent = issue['fields'].get('parent', {}).get('key')
        parent_summary = issue['fields'].get('parent', {}).get('fields', {}).get('summary', summary)
        data.append({"Parent summary": parent_summary, "Minutes": minutes})

    df = pd.DataFrame(data)
    if df.empty:
        st.warning("해당 조건에 맞는 이슈가 없습니다.")
        return

    summary = df.groupby("Parent summary")["Minutes"].sum().reset_index()
    summary["Minutes"] = summary["Minutes"].astype(int)

    st.subheader("📊 Parent Summary별 Original Estimate (분)")
    st.dataframe(summary)

    total = summary["Minutes"].sum()
    formatted = minutes_to_dhm(total)
    st.markdown(f"### 🧮 총합: {total}분  ")
    st.markdown(f"- 약 {total // 60}시간 {total % 60}분")
    st.markdown(f"- 📅 근무일 기준 포맷: **{formatted}**")

# Streamlit UI 시작
st.title("🧾 Jira Original Estimate 요약 도구")

config = load_config()
email = config.get("email", "")
api_token = config.get("api_token", "")
project = config.get("project", "")

with st.expander("🔐 설정 변경"):
    email = st.text_input("Jira 이메일", value=email)
    api_token = st.text_input("Jira API Token", value=api_token, type="password")
    project = st.text_input("기본 프로젝트 키", value=project)
    if st.button("설정 저장"):
        save_config(email, api_token, project)
        st.success("설정이 저장되었습니다.")

fix_version = st.text_input("📦 Fix Version (예: 2025.04.30)")
authors_input = st.text_input("✍️ 작성자들을 쉼표로 입력 (예: yeoung004, user2)")

if st.button("Jira에서 데이터 가져오기"):
    if not all([email, api_token, project, fix_version, authors_input]):
        st.error("모든 항목을 입력해 주세요.")
    else:
        jira_url = "https://acloset.atlassian.net"
        authors = [a.strip() for a in authors_input.split(',')]
        author_clause = " or ".join([f"reporter = {a}" for a in authors])
        jql = f"project = {project} AND fixVersion = \"{fix_version}\" AND ({author_clause})"
        summarize_issues_from_api(jira_url, jql, email, api_token)
Ø