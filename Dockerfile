# Dockerfile

# --- Stage 1: Builder ---
# This stage installs dependencies into a temporary location.
FROM python:3.11-slim as builder

# Set the working directory
WORKDIR /app

# Install build tools needed for some packages
RUN apt-get update && apt-get install -y --no-install-recommends build-essential

# Copy requirements file and install dependencies
# This leverages Docker's layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix="/install" -r requirements.txt


# --- Stage 2: Final Image ---
# This stage builds the final, lean image.
FROM python:3.11-slim

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Set the working directory
WORKDIR /app

# Copy installed packages from the builder stage
COPY --from=builder /install /usr/local

# Copy the application code
COPY bot.py gunicorn.conf.py ./

# Ensure the logs directory exists and is owned by the appuser
RUN mkdir -p /app/logs && chown -R appuser:appuser /app

# Change ownership of the application code
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Expose the port the app will run on
# This is for documentation; Koyeb will map its own port.
EXPOSE 8000

# The command to run the application
CMD ["gunicorn", "-c", "gunicorn.conf.py", "bot:app"]
