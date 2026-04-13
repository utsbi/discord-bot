FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY steve/ steve/

CMD ["uv", "run", "python", "steve/main.py"]
