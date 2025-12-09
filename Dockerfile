# TODO: Add containerization steps. Example baseline:
# FROM python:3.11-slim
# WORKDIR /app
# COPY pyproject.toml README.md ./
# COPY src ./src
# COPY docs ./docs
# RUN pip install uv && uv sync
# CMD ["streamlit", "run", "src/app/main_streamlit.py", "--server.port=8501", "--server.address=0.0.0.0"]
