FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 git && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY pyproject.toml ./
RUN python -c "import tomllib; deps = tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']; print('\n'.join(deps))" > /tmp/deps.txt && \
    pip install --no-cache-dir -r /tmp/deps.txt

COPY app/ ./app/
COPY projarvis/ ./projarvis/
RUN pip install --no-cache-dir --no-deps . && mkdir -p /app/config/state

ENV TZ=Asia/Shanghai
EXPOSE 8000
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8000"]
