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

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
