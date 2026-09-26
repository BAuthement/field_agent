FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py db.py i18n.py curriculum.py assistant.py reports.py ./
COPY templates ./templates
COPY static ./static
COPY curriculum ./curriculum
RUN mkdir -p /app/data
# SQLite default path (used only when DATABASE_URL is not set).
ENV FIELD_AGENT_DB=/app/data/field-agent.db
ENV PORT=5000
EXPOSE 5000
# ${PORT} lets hosts like Render/Fly inject their own port; logs go to stdout.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --access-logfile - --error-logfile - app:app"]
