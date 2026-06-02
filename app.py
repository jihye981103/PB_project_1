import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import pandas as pd
import os
import urllib.request
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfbase import pdfmetrics
from reportlab.lib.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors

# --- 1. 경로 및 설정 ---
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
JSON_KEY_FILE = os.path.join(BASE_PATH, "key.json")
LOGO_IMAGE_PATH = os.path.join(BASE_PATH, "logo.png")

# 로컬과 서버 모두에서 작동하는 한글 폰트 자동 다운로드 로직
FONT_PATH = os.path.join(BASE_PATH, "NanumGothic.ttf")
if not os.path.exists(FONT_PATH):
    with st.spinner("한글 폰트를 준비 중입니다..."):
        font_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
        urllib.request.urlretrieve(font_url, FONT_PATH)

# 사용자가 보내주신 고유 ID 반영 (교정 완료)
SHEET_ID = "1EiaKCUJU9O5ajNzUwVOq542aVc8CTw8oFbLaeI9xeHI"
FOLDER_ID = "1INlxagsBpkYmm4rGM2CqB2wtM_oa6EAW"

# --- 2. 폰트 등록 ---
try:
    pdfmetrics.registerFont(TTFont("NanumGothic", FONT_PATH))
except Exception as e:
    st.error(f"폰트 등록 실패: {e}")

# --- 3. 구글 API 인증 연결 ---
@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    if os.path.exists(JSON_KEY_FILE):
        creds = Credentials.from_service_account_file(JSON_KEY_FILE, scopes=scopes)
    else:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    
    client = gspread.authorize(creds)
    drive_service = build("drive", "v3", credentials=creds)
    return client, drive_service

try:
    gc, drive_service = get_gspread_client()
except Exception as e:
    st.error(f"구글 인증 실패: {e}")
    st.stop()

# --- 4. 데이터 불러오기 ---
@st.cache_data(ttl=60)
def load_data():
    sh = gc.open_by_key(SHEET_ID)
    worksheet = sh.get_worksheet(0)
    data = worksheet.get_all_records()
    return pd.DataFrame(data)

try:
    df_origin = load_data()
except Exception as e:
    st.error(f"시트 데이터를 가져오지 못했습니다: {e}")
    st.stop()

# --- 5. 스트림릿 UI 디자인 시작 ---
st.set_page_config(page_title="PB 상품 카탈로그 시스템", layout="wide")

st.markdown("# 📂 PB 상품 카탈로그 시스템")
st.write("---")

# 카테고리 선택 필터
if "카테고리" in df_origin.columns:
    categories = df_origin["카테고리"].unique().tolist()
    selected_cats = st.multiselect("1. 카테고리 선택", categories, default=categories)
    df_filtered = df_origin[df_origin["카테고리"].isin(selected_cats)].copy()
else:
    df_filtered = df_origin.copy()

st.markdown("### 2. 품목 선택 및 데이터 수정")
st.write("팁: 표 안의 '품목명(수정가능)' 셀을 더블클릭하여 이름을 고친 후 PDF를 뽑을 수 있습니다.")

# 에디터 표 구성을 위한 컬럼 정리
display_cols = ["품목코드", "품목명", "카테고리", "규격", "보관방법", "발주단위", "소비기한", "알레르기유발성분"]
available_cols = [c for c in display_cols if c in df_filtered.columns]

if "품목명" in df_filtered.columns:
    df_filtered.rename(columns={"품목명": "품목명(수정가능)"}, inplace=True)
    idx = available_cols.index("품목명")
    available_cols[idx] = "품목명(수정가능)"

# 선택(체크박스) 기능 추가
df_filtered.insert(0, "선택", True)

# 데이터프레임 에디터 표시
edited_df = st.data_editor(
    df_filtered,
    column_config={
        "선택": st.column_config.CheckboxColumn(default=True),
        "품목코드": st.column_config.NumberColumn(format="%d", disabled=True),
        "카테고리": st.column_config.TextColumn(disabled=True),
        "규격": st.column_config.TextColumn(disabled=True),
    },
    disabled=[c for c in df_filtered.columns if c != "선택" and c != "품목명(수정가능)"],
    hide_index=True,
    use_container_width=True
)

# 최종 선택된 품목만 필터링
selected_items = edited_df[edited_df["선택"] == True]

# --- 6. PDF 카탈로그 생성 함수 ---
def create_pdf(dataframe):
    pdf_filename = "PB_Catalog.pdf"
    c = canvas.Canvas(pdf_filename, pagesize=A4)
    width, height = A4
    
    # 상단 배너 베이지색 디자인
    c.setFillColor(colors.HexColor("#F7F3E9"))
    c.rect(0, height - 80, width, 80, fill=1, stroke=0)
    
    c.setFillColor(colors.HexColor("#333333"))
    c.setFont("NanumGothic", 22)
    c.drawString(40, height - 50, "PB PRODUCT CATALOG")
    
    c.setFont("NanumGothic", 10)
    c.setFillColor(colors.HexColor("#666666"))
    c.drawString(40, height - 110, f"총 {len(dataframe)}개의 품목이 수록되어 있습니다.")
    
    # 표 헤더 (블루 바)
    y_pos = height - 140
    c.setFillColor(colors.HexColor("#7A8FB7"))
    c.rect(40, y_pos, width - 80, 20, fill=1, stroke=0)
    
    c.setFillColor(colors.white)
    c.setFont("NanumGothic", 10)
    c.drawString(50, y_pos + 5, "카테고리")
    c.drawString(130, y_pos + 5, "품목명")
    c.drawString(350, y_pos + 5, "규격")
    c.drawString(480, y_pos + 5, "보관방법")
    
    y_pos -= 25
    c.setFillColor(colors.black)
    
    for _, row in dataframe.iterrows():
        if y_pos < 50:
            c.showPage()
            c.setFont("NanumGothic", 10)
            y_pos = height - 50
            
        cat = str(row.get("카테고리", ""))
        p_name = str(row.get("품목명(수정가능)", row.get("품목명
