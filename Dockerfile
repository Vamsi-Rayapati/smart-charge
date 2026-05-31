# Use an official, lightweight Python image.
FROM python:3.11-slim

# Prevent Python from writing .pyc files (keeps container clean)
# and enable unbuffered stdout/stderr logging for live container outputs.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the Python path so our modules inside src/ are discoverable
ENV PYTHONPATH=/app

# Set the working directory inside the container.
WORKDIR /app

# Install minimal OS requirements for building/running standard tools.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only the requirements first to maximize Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose Streamlit default port
EXPOSE 8501

# Run the Streamlit application
CMD ["streamlit", "run", "src/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
