FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /testcase-doc-rag

# requirements 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 코드 복사
COPY ./app /testcase/app

# test_images 디렉토리 및 데이터 복사
COPY ./test_images /testcase-doc-rag/test_images

# 환경변수 설정
ENV PYTHONPATH=/testcase-doc-rag

# 포트 노출
EXPOSE 8000

# 앱 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "5"]