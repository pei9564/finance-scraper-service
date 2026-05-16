FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 先裝依賴（利用 layer cache）
COPY pyproject.toml requirements.txt ./
RUN pip install -r requirements.txt

# 再複製原始碼並 editable 安裝（讓 `python -m tech_intel.*` 找得到）
COPY src ./src
RUN pip install -e .

EXPOSE 8080

CMD ["python", "-m", "tech_intel.server"]
