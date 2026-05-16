FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080

WORKDIR /app

# 先裝依賴（利用 layer cache）
COPY pyproject.toml requirements.txt ./
RUN pip install -r requirements.txt

# 再複製原始碼並 editable 安裝（讓 `python -m finance_scraper.*` 找得到）
COPY src ./src
RUN pip install -e .

# 內建一份預設 config；k3s 可用 ConfigMap 掛 /app/config 覆蓋，
# local compose 也會 mount ./config 覆蓋這份預設。
COPY config ./config

# Non-root：k3s 若啟用 PodSecurity restricted 不會擋
RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["python", "-m", "finance_scraper.server"]
