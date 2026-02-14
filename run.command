#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$PROJECT_DIR/venv_estro/bin/python"
VENV_STREAMLIT="$PROJECT_DIR/venv_estro/bin/streamlit"

cd "$PROJECT_DIR"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "venv_estro/bin/python 을 찾을 수 없습니다: $VENV_PYTHON"
    echo "먼저 가상환경을 생성하세요. (예: python3 -m venv venv_estro)"
    exit 1
fi

if [ ! -x "$VENV_STREAMLIT" ]; then
    echo "venv_estro에 streamlit이 설치되지 않았습니다."
    echo "실행: $VENV_PYTHON -m pip install -r requirements.txt"
    exit 1
fi

# 원격 저장소(GitHub 등)에서 최신 변경사항이 있는지 확인하고 가져옵니다.
if git rev-parse --git-dir > /dev/null 2>&1; then
    echo "최신 코드를 확인 중..."
    git pull origin main || true
fi

echo "EstroFrame을 실행 중입니다..."
exec "$VENV_STREAMLIT" run "$PROJECT_DIR/main.py"
