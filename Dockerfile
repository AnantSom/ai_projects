FROM python:3.10-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Expose port
EXPOSE 10000

# Use gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "2", "app:app"]