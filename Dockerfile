FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Some local setups (antivirus TLS inspection) break certificate verification
# inside the build container. On those machines build with:
#   --build-arg PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org"
# Leave unset everywhere else (CI, normal networks) so TLS stays verified.
ARG PIP_TRUSTED_HOST=
ENV PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --no-cache-dir .

# Run as an unprivileged user - a container escape shouldn't land as root.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
