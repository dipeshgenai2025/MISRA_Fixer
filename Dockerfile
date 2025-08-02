# ==============================================================================
# File: Dockerfile
#
# Description: This Dockerfile uses a multi-stage build to create a lean and
#              efficient Docker image for the MISRA Smart Fixer application.
#
# Author: Dipesh Karmakar
#
# Version: 1.0
# ==============================================================================

# Stage 1: The builder stage to compile llama-cpp-python with CUDA support
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04 AS builder

WORKDIR /app

# Install build dependencies, including the CUDA toolkit, git, and g++-9
# These are necessary to compile llama-cpp-python from source with CUDA support.
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip ninja-build build-essential nvidia-cuda-toolkit git g++-9 && \
    rm -rf /var/lib/apt/lists/*

# Set the environment variables for the llama-cpp-python build.
# GGML_CUDA=on enables GPU support.
# We explicitly set the host compiler using a CMake flag to resolve the g++-11 incompatibility.
ENV CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-9"

# Copy requirements and build a wheel for llama-cpp-python.
# We build a wheel here so we can install it cleanly in the next stage.
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels --no-cache-dir -r requirements.txt

# --- End of Builder Stage ---

# Stage 2: The final, smaller runtime image
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

WORKDIR /app

# Install only the runtime dependencies (cppcheck, python, libgomp1, libcudart11.0, and libcublas11)
# libgomp1 is required for llama-cpp-python's OpenMP support.
# libcudart11.0 and libcublas11 are required to resolve the missing shared object file dependencies.
# To install these, we must first add the CUDA 11.x repository.
RUN apt-get update && \
    apt-get install -y --no-install-recommends software-properties-common wget && \
    wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb && \
    dpkg -i cuda-keyring_1.1-1_all.deb && \
    apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip cppcheck libgomp1 libcudart11.0 libcublas11 && \
    rm -rf /var/lib/apt/lists/* cuda-keyring_1.1-1_all.deb

ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Copy the pre-built wheels from the builder stage and install them
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*

# Copy the application files and the large model file
COPY app.py .
COPY codellama-7b-instruct.Q4_K_M.gguf /app/codellama-7b-instruct.Q4_K_M.gguf

# Expose the application port
EXPOSE 7860

ENV PYTHONUNBUFFERED=1

# Define the command to run the application
CMD ["python3", "app.py"]
