# Use official Python base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements and application
COPY requirements.txt ./
COPY kopia_influxdb_webhook_plugin.py ./

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 5000

# Run the Flask app
CMD ["python", "kopia_influxdb_webhook_plugin.py"]