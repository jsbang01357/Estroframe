import webview
import multiprocessing
import time
import os
import sys
import streamlit.web.cli as stcli

def resolve_path(path):
    """실행 파일로 패키징되었을 때 임시 경로(_MEIPASS)를 찾아주는 함수"""
    if getattr(sys, 'frozen', False):
        basedir = sys._MEIPASS
    else:
        basedir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(basedir, path)

def run_streamlit():
    """Streamlit 서버를 실행하는 함수"""
    main_script = resolve_path("main.py")
    sys.argv = [
        "streamlit", "run", main_script,
        "--server.headless", "true",
        "--server.port", "8501",
        "--global.developmentMode=false"
    ]
    stcli.main()

def start_logic():
    # 1. Streamlit 서버를 별도 프로세스로 실행
    p = multiprocessing.Process(target=run_streamlit)
    p.start()

    # 2. 서버 예열 대기 (의학적 마취 시간)
    time.sleep(5)

    # 3. Pywebview 창 생성 및 실행
    try:
        window = webview.create_window('EstroFrame', 'http://localhost:8501', width=1280, height=850)
        webview.start()
    finally:
        # 4. 창을 닫으면 서버 프로세스 종료
        p.terminate()
        p.join()

if __name__ == "__main__":
    multiprocessing.freeze_support()  # Windows 패키징 필수
    start_logic()