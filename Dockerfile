FROM python:3.14-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY app/ app/
RUN pip install --no-cache-dir .

CMD ["fastapi", "run"]