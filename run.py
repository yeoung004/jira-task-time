import pandas as pd
import re
import requests
import streamlit as st
from requests.auth import HTTPBasicAuth

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
        "fields": "summary,parent,timetracking,assignee,status"
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
        parent_summary = issue['fields'].get('parent', {}).get('fields', {}).get('summary', summary)
        data.append({"Parent summary": parent_summary, "Minutes": minutes})

    df = pd.DataFrame(data)
    if df.empty:
        st.warning("해당 조건에 맞는 이슈가 없습니다.")
        return

    summary = df.groupby("Parent summary")["Minutes"].sum().reset_index()
    summary["Minutes"] = summary["Minutes"].astype(int)

    with st.expander("📊 스토리별 할당시간 (분)", expanded=True):
        st.dataframe(summary)

    total = summary["Minutes"].sum()
    formatted = minutes_to_dhm(total)
    with st.expander("🧮 총합 및 근무일 기준 포맷", expanded=True):
        st.markdown(f"### 🧮 총합: {total}분  ")
        st.markdown(f"- 약 {total // 60}시간 {total % 60}분")
        st.markdown(f"- 📅 근무일 기준 포맷: ***{formatted}***")

    # 사람별로 각각 할당 시간 계산 (assignee를 사람이름으로 필터링)
    authors = [a.strip() for a in st.session_state.authors_input.split(',') if a.strip()]
    if authors:
        with st.expander("👤 사람별 할당 시간", expanded=True):
            person_minutes = {author: 0 for author in authors}
            for issue in issues:
                assignee = issue['fields'].get('assignee', None)
                if assignee:
                    assignee_name = assignee.get('displayName') or assignee.get('name') or assignee.get('emailAddress') or ''
                    assignee_name = assignee_name.strip()
                    estimate = issue['fields'].get('timetracking', {}).get('originalEstimateSeconds', 0)
                    minutes = int(estimate / 60) if estimate else 0
                    for author in authors:
                        # assignee_name이 정확히 author와 일치할 때만 할당
                        if author == assignee_name:
                            person_minutes[author] += minutes
            for author in authors:
                m = person_minutes[author]
                m_fmt = minutes_to_dhm(m)
                st.markdown(f"- {author}: {m}분 (근무일 기준: {m_fmt})")

    # 작업대기/작업중 상태만 사람별로 집계
    authors = [a.strip() for a in st.session_state.authors_input.split(',') if a.strip()]
    waiting_statuses = ['To Do', '대기', '작업 대기', 'In Progress', '진행중', '진행 중', '작업 중']
    if authors:
        with st.expander("👤 작업대기/작업중 상태 사람별 할당 시간", expanded=False):
            person_minutes = {author: 0 for author in authors}
            for issue in issues:
                # 상태명: 이슈 status → parent status
                status_name = issue['fields'].get('status', {}).get('name', '').strip()
                if not status_name and 'parent' in issue['fields']:
                    status_name = issue['fields']['parent'].get('fields', {}).get('status', {}).get('name', '').strip()
                if status_name in waiting_statuses:
                    assignee = issue['fields'].get('assignee', None)
                    if assignee:
                        assignee_name = assignee.get('displayName') or assignee.get('name') or assignee.get('emailAddress') or ''
                        assignee_name = assignee_name.strip()
                        estimate = issue['fields'].get('timetracking', {}).get('originalEstimateSeconds', 0)
                        minutes = int(estimate / 60) if estimate else 0
                        for author in authors:
                            if author == assignee_name:
                                person_minutes[author] += minutes
            for author in authors:
                m = person_minutes[author]
                m_fmt = minutes_to_dhm(m)
                st.markdown(f"- {author}: {m}분 (근무일 기준: {m_fmt})")

def update_email():
    st.session_state.email = st.session_state.email_input

def update_api_token():
    st.session_state.api_token = st.session_state.api_token_input

def update_project():
    st.session_state.project = st.session_state.project_input

def update_fix_version():
    st.session_state.fix_version = st.session_state.fix_version_input

def update_authors_input():
    st.session_state.authors_input = st.session_state.authors_input_key

# Streamlit UI 시작
st.title("🧾스토리별 할당 시간 요약 도구")

# 기본 변수 값 설정
if 'email' not in st.session_state:
    st.session_state.email = ""
if 'api_token' not in st.session_state:
    st.session_state.api_token = ""
if 'project' not in st.session_state:
    st.session_state.project = ""
if 'fix_version' not in st.session_state:
    st.session_state.fix_version = ""
if 'authors_input' not in st.session_state:
    st.session_state.authors_input = ""

# 사이드바에 설정 입력 필드 생성
with st.sidebar:
    st.header("🔑 Jira 계정 설정")
    with st.form("jira_form"):
        email = st.text_input("Jira 이메일", value=st.session_state.email, placeholder="you@example.com")
        api_token = st.text_input("Jira API Token", value=st.session_state.api_token, placeholder="API Token", type="password")
        project = st.text_input("기본 프로젝트 키 (예: AG)", value=st.session_state.project, placeholder="AG")
        fix_version = st.text_input("📦 Fix Version (예: APP 6.0.0)", value=st.session_state.fix_version)
        authors_input = st.text_input("✍️ 작성자들을 쉼표로 입력 (예: 최영성, 여진석)", value=st.session_state.authors_input)
        submitted = st.form_submit_button("입력값 저장")
        if submitted:
            st.session_state.email = email
            st.session_state.api_token = api_token
            st.session_state.project = project
            st.session_state.fix_version = fix_version
            st.session_state.authors_input = authors_input

# 모든 입력값 자동 저장
st.session_state.fix_version = fix_version
st.session_state.authors_input = authors_input

# 입력값이 모두 채워졌는지 실시간 체크
all_filled = all([
    st.session_state.email,
    st.session_state.api_token,
    st.session_state.project,
    st.session_state.fix_version,
    st.session_state.authors_input
])

if not all_filled:
    st.warning("모든 항목을 입력해 주세요. (자동완성 사용 시 입력란을 한 번 클릭하거나 엔터를 눌러주세요)")
else:
    if st.button("Jira에서 데이터 가져오기"):
        jira_url = "https://acloset.atlassian.net"
        authors = [a.strip() for a in st.session_state.authors_input.split(',')]
        author_clause = " or ".join([f"assignee = {a}" for a in authors])
        jql = f"project = {st.session_state.project} AND fixVersion = \"{st.session_state.fix_version}\" AND ({author_clause})"
        summarize_issues_from_api(jira_url, jql, st.session_state.email, st.session_state.api_token)