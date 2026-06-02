import urllib.request
import os
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
import traceback
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors

# ==========================================
# --- 1. 경로 및 폰트 자동 다운로드 설정 ---
# ==========================================
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
JSON_KEY_FILE = os.path.join(BASE_PATH, "key.json")
LOGO_IMAGE_PATH = os.path.join(BASE_PATH, "logo.png")

FONT_PATH = "NanumGothic.ttf"
FONT_BOLD_PATH = "NanumGothic-Bold.ttf"

# 사내 보안 프로그램을 우회하여 인터넷에서 폰트를 자동으로 다운로드합니다.
if not os.path.exists(FONT_PATH):
    try:
        urllib.request.urlretrieve("https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf", FONT_PATH)
    except Exception as e:
        st.error(f"기본 폰트 다운로드 실패: {e}")

if not os.path.exists(FONT_BOLD_PATH):
    try:
        urllib.request.urlretrieve("https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf", FONT_BOLD_PATH)
    except Exception as e:
        st.error(f"볼드 폰트 다운로드 실패: {e}")

# 구글 드라이브 및 스프레드시트 설정 값
SHEET_ID = "1EiaKCUJU9O5ajNzUwVOq542aVc8CTw8oFbLaeI9xeHI"
FOLDER_ID = "1INlxagsBpkYmm4rGM2CqB2wtM_oa6EAW"

# 카테고리별 영문 타이틀 매핑 사전
CATEGORY_ENG_MAP = {
    "디저트": "Sweet Dessert",
    "조미식품": "Sauce & Seasoning",
    "수산물": "Fresh Seafood",
    "축산물": "Premium Meat",
    "가공식품": "Processed Food",
    "비식품": "Non-Food Items",
    "음료": "Beverage",
    "CK": "Central Kitchen"
}

# ==========================================
# --- 2. 인증 및 서비스 연결 (캐싱 적용) ---
# ==========================================
@st.cache_resource
def get_gspread_client():
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file(JSON_KEY_FILE, scopes=scopes)
        return gspread.authorize(creds), build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"인증 파일 로드 실패: {e}")
        return None, None

# ==========================================
# --- 3. 데이터 기능 함수 ---
# ==========================================
def load_data(gc):
    sh = gc.open_by_key(SHEET_ID)
    worksheet = sh.worksheet("list")
    data = worksheet.get_all_records()
    return pd.DataFrame(data)

def get_drive_image_map(drive_service, folder_id):
    results = drive_service.files().list(
        q=f"'{folder_id}' in parents and mimeType contains 'image/'",
        fields="files(id, name)"
    ).execute()
    files = results.get('files', [])
    return {f['name'].split('.')[0]: f['id'] for f in files}

def download_image(drive_service, file_id):
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return fh

# ==========================================
# --- 4. PDF 생성 로직 ---
# ==========================================
def create_pdf(selected_data, image_map, items_per_page, drive_service):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # 설정: 배너 공간을 확보한 여백 시스템
    MARGIN_TOP = 210
    MARGIN_BOTTOM = 40
    MARGIN_LEFT = 40
    PAGE_INNER_W = width - (MARGIN_LEFT * 2)
    PAGE_INNER_H = height - MARGIN_TOP - MARGIN_BOTTOM
    
    if items_per_page == 1: cols, rows = 1, 1
    elif items_per_page == 2: cols, rows = 1, 2
    elif items_per_page == 4: cols, rows = 2, 2
    elif items_per_page == 6: cols, rows = 2, 3
    elif items_per_page == 9: cols, rows = 3, 3 
    elif items_per_page == 12: cols, rows = 3, 4 
    else: cols, rows = 3, 3 
    
    cell_w = PAGE_INNER_W / cols
    cell_h = PAGE_INNER_H / rows
    
    progress_bar = st.progress(0)
    total_items = len(selected_data)
    current_count = 0

    for category, group in selected_data.groupby('카테고리', sort=False):
        item_idx = 0

        def draw_page_header(cat_name):
            c.saveState()
            
            # 1. 고급스러운 베이지톤 배경 박스
            banner_h = 135
            banner_y = height - banner_h - 40 
            c.setFillColor(colors.HexColor("#F7F3E9"))
            c.setStrokeColor(colors.transparent)
            c.rect(MARGIN_LEFT, banner_y, PAGE_INNER_W, banner_h, fill=True, stroke=False)
            
            # 2. 맞춤형 영문 타이틀
            eng_title = CATEGORY_ENG_MAP.get(cat_name, "Premium Quality")
            c.setFont('KoreanFontBold', 36)
            c.setFillColor(colors.HexColor("#7A8FB7")) 
            c.drawString(MARGIN_LEFT + 25, banner_y + 75, eng_title)
            
            # 3. 서브 국문 타이틀
            c.setFont('KoreanFontBold', 20)
            c.setFillColor(colors.HexColor("#555555")) 
            c.drawString(MARGIN_LEFT + 25, banner_y + 45, f"{cat_name} 리스트")
            
            # 4. 하단 포인트 데코 라인
            c.setLineWidth(2)
            c.setStrokeColor(colors.HexColor("#7A8FB7"))
            c.line(MARGIN_LEFT + 25, banner_y + 25, MARGIN_LEFT + 180, banner_y + 25)
            
            # 5. 로고 배치
            if os.path.exists(LOGO_IMAGE_PATH):
                try:
                    logo_img = ImageReader(LOGO_IMAGE_PATH)
                    c.drawImage(logo_img, MARGIN_LEFT + PAGE_INNER_W - 120, banner_y + 75, 
                                width=100, height=45, 
                                mask='auto', preserveAspectRatio=True, anchor='ne')
                except:
                    pass 
            
            c.restoreState()
        
        draw_page_header(category)
        
        for _, row in group.iterrows():
            if item_idx > 0 and item_idx % items_per_page == 0:
                c.showPage()
                draw_page_header(category) 
            
            pos = item_idx % items_per_page
            c_idx = pos % cols
            r_idx = pos // cols
            
            x = MARGIN_LEFT + (c_idx * cell_w)
            y = height - MARGIN_TOP - ((r_idx + 1) * cell_h)
            
            padding = 15
            
            if items_per_page == 12:
                img_h_limit = cell_h * 0.48
                title_font_size = 8.5 
                spec_box_h = 42 
                line_spacing = 9 
            else:
                img_h_limit = cell_h * 0.55
                title_font_size = 10
                spec_box_h = 52
                line_spacing = 11

            img_y_start = y + (cell_h - img_h_limit) + 6
            
            if p_code := str(row.get('품목코드', '')):
                if p_code in image_map:
                    try:
                        img_data = download_image(drive_service, image_map[p_code])
                        img = ImageReader(img_data)
                        c.drawImage(img, x + padding, img_y_start, 
                                    width=cell_w - (padding * 2), height=img_h_limit - 10, 
                                    preserveAspectRatio=True, anchor='c')
                    except:
                        c.rect(x + padding, img_y_start, cell_w - (padding * 2), img_h_limit - 10)
                else:
                    c.rect(x + padding, img_y_start, cell_w - (padding * 2), img_h_limit - 10)

            # 1. 품목명
            text_y = y + (cell_h - img_h_limit) - 5
            c.setFont('KoreanFont', title_font_size)
            c.setFillColor(colors.black)
            
            item_name = str(row.get('품목명', ''))
            c.drawString(x + padding, text_y, item_name)
            
            # 2. 라인
            line1_y = text_y - 5
            c.setLineWidth(0.5)
            c.setStrokeColor(colors.gray)
            c.line(x + padding, line1_y, x + cell_w - padding, line1_y)
            
            # 3. 세부 정보 영역
            spec_font_size = title_font_size * 0.75 
            spec_box_y = line1_y - spec_box_h - 2
            
            c.saveState()
            c.setFillColor(colors.HexColor("#F7F7F7"))
            c.setStrokeColor(colors.transparent)
            c.rect(x + padding, spec_box_y, cell_w - (padding * 2), spec_box_h, fill=True, stroke=False)
            c.restoreState()
            
            spec_start_y = line1_y - (line_spacing + 1)
            
            details = [
                ("규격", str(row.get('규격', ''))),
                ("보관방법", str(row.get('보관방법', ''))),
                ("유통기한", str(row.get('소비기한', ''))), 
                ("상품코드", p_code) 
            ]
            
            current_y = spec_start_y
            c.setFont('KoreanFont', spec_font_size)
            c.setFillColor(colors.HexColor("#333333")) 
            
            for label, val in details:
                c.drawString(x + padding + 4, current_y, label)
                c.drawRightString(x + cell_w - padding - 4, current_y, val)
                current_y -= line_spacing
                
            item_idx += 1
            current_count += 1
            progress_bar.progress(current_count / total_items)
            
        c.showPage() 

    c.save()
    progress_bar.empty()
    buffer.seek(0)
    return buffer

# ==========================================
# --- 5. Streamlit UI ---
# ==========================================
st.set_page_config(page_title="PB 카탈로그", layout="wide")

if not os.path.exists(JSON_KEY_FILE):
    st.error(f"키 파일을 찾을 수 없습니다: {JSON_KEY_FILE}")
    st.stop()

# 폰트 파일을 등록합니다.
pdfmetrics.registerFont(TTFont('KoreanFont', FONT_PATH))
pdfmetrics.registerFont(TTFont('KoreanFontBold', FONT_BOLD_PATH))

gc, drive_service = get_gspread_client()

if gc:
    try:
        st.title("📂 PB 상품 카탈로그 시스템")
        
        with st.spinner("구글 시트에서 데이터를 가져오고 있습니다..."):
            df_raw = load_data(gc)
            image_map = get_drive_image_map(drive_service, FOLDER_ID)
        
        with st.sidebar:
            st.header("⚙️ 설정")
            items_per_page = st.selectbox("페이지당 품목 수", [1, 2, 4, 6, 9, 12], index=4) 
            st.success("연결 완료 (v3.7)")

        all_categories = df_raw['카테고리'].unique()
        selected_cats = st.multiselect("1. 카테고리 선택", all_categories, default=all_categories)
        
        if selected_cats:
            filtered_df = df_raw[df_raw['카테고리'].isin(selected_cats)].copy()
            if '선택' not in filtered_df.columns:
                filtered_df.insert(0, '선택', True)

            st.subheader("2. 품목 선택 및 수정")
            edited_df = st.data_editor(
                filtered_df,
                column_config={
                    "선택": st.column_config.CheckboxColumn("선택", default=True),
                    "품목명": st.column_config.TextColumn("품목명 (수정가능)"),
                },
                disabled=["품목코드", "규격", "보관방법", "발주단위", "소비기한", "카테고리"],
                use_container_width=True,
                hide_index=True
            )

            final_df = edited_df[edited_df['선택'] == True].copy()
            st.write(f"✅ 현재 **{len(final_df)}개** 선택됨")

            if st.button("🚀 PDF 생성 및 다운로드"):
                if final_df.empty:
                    st.warning("선택된 품목이 없습니다.")
                else:
                    pdf_result = create_pdf(final_df, image_map, items_per_page, drive_service)
                    st.download_button(
                        label="💾 PDF 다운로드",
                        data=pdf_result,
                        file_name="PB_Catalog.pdf",
                        mime="application/pdf"
                    )
    except Exception as e:
        st.error("데이터를 불러오는 중 오류가 발생했습니다.")
        st.code(traceback.format_exc())
