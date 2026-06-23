FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/home/appuser/.local/bin:${PATH}"

WORKDIR /app

RUN addgroup --system --gid 10001 appuser \
    && adduser --system --uid 10001 --ingroup appuser --home /home/appuser appuser

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

RUN pip install --upgrade pip \
    && python -c "import pathlib, tomllib; data = tomllib.loads(pathlib.Path('pyproject.toml').read_text()); print('\n'.join(data['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

USER 10001:10001

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
