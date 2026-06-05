# Use an official lightweight Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Set the working directory in the container
WORKDIR /app

# Install system dependencies needed for OpenCV, PyTorch, and compiling packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libglib2.0-0 \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
# Note: We install CPU-only versions of torch and torchvision to keep the image small
# and prevent build timeouts on Render (which has a 10-minute build limit on the free tier).
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create necessary directories for local data persistence
RUN mkdir -p data/faces data/virtual_class weights

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application (Render will automatically override PORT if specified)
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
