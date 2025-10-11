FROM python:3.11-slim

# Prevent writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# copy requirements file
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the application
COPY . .

# Expose the dashboard port
EXPOSE 22222

# start dashboard server
CMD ["python", "-m", "apiwatch"]

