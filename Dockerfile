FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app

# Environment setup
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

EXPOSE 10000

CMD ["python", "app.py"]
