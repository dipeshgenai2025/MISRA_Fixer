# MISRA Smart Fixer using GenAI: Installation and Usage Guide

This guide provides step-by-step instructions for setting up and running the MISRA Smart Fixer application, which uses `cppcheck` and a local Large Language Model (LLM) to automatically fix MISRA C/C++ violations.

The application is containerized using Docker, with support for GPU acceleration via the NVIDIA Container Toolkit and CPU only mode as well.

## Prerequisites

* A Windows PC with WSL (if not running a native Linux distribution)
* NVIDIA GPU with the latest drivers installed (For GPU Only mode)
* Docker Engine installed and configured
* NVIDIA Container Toolkit installed and configured for Docker (For GPU Only mode)

## 1. Setting up the Environment

This section outlines the necessary steps to prepare your system for the application.

### A. Windows Subsystem for Linux (WSL)

If you are on a Windows machine, you must install WSL to enable full GPU access within your Docker containers.

1.  **List Available Distributions:**
    ```sh
    wsl --list --online
    ```

2.  **Install a Linux Distribution:**
    We recommend using Ubuntu 22.04, as it's well-supported for the required dependencies.
    ```sh
    wsl --install -d Ubuntu-22.04
    ```

3.  **Optimize WSL (Optional but Recommended):**
    Periodically optimize the WSL virtual hard disk to improve performance. Replace `XXX` with your username and verify the path.
    ```powershell
    Optimize-VHD -Path "C:\Users\XXX\AppData\Local\Packages\CanonicalGroupLimited.Ubuntu22.04LTS_79rhkp1fndgsc\LocalState\ext4.vhdx" -Mode Full
    ```

### B. Installing Docker and NVIDIA Container Toolkit

1.  **Install Docker Engine on Ubuntu:**
    Follow the official Docker documentation for installing Docker Engine on Ubuntu:
    [https://docs.docker.com/engine/install/ubuntu/](https://docs.docker.com/engine/install/ubuntu/)

2.  **Install the NVIDIA Container Toolkit:**
    This toolkit is crucial for enabling GPU access inside your Docker containers.
    ```sh
    distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
    curl -s -L [https://nvidia.github.io/libnvidia-container/gpgkey](https://nvidia.github.io/libnvidia-container/gpgkey) | sudo apt-key add -
    curl -s -L [https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list](https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list) | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

    sudo apt-get update
    sudo apt-get install -y nvidia-container-toolkit

    # Configure and restart Docker
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
    ```

3.  **Install a Text Editor:**
    For convenience, install a GUI text editor like Gedit.
    ```sh
    sudo apt install gedit
    ```

## 2. Running the Application

This section guides you through cloning the repository, building the Docker image, and running the application.

1.  **Clone the Repository:**
    ```sh
    git clone https://github.com/dipeshgenai2025/MISRA_Fixer
    cd MISRA_Fixer
    ```

2.  **Download the LLM Model:**
    Download the required GGUF model file. This guide uses `codellama-7b-instruct.Q4_K_M.gguf`. You can choose a different model to optimize the output as needed.
    ```sh
    wget https://huggingface.co/TheBloke/CodeLlama-7B-Instruct-GGUF/resolve/main/codellama-7b-instruct.Q4_K_M.gguf
    ```

3.  **Build the Docker Image:**
    Build the Docker image with GPU support, passing the local model file as a build argument.
    ```sh
    sudo DOCKER_BUILDKIT=1 docker build --build-arg MODEL_FILE=./codellama-7b-instruct.Q4_K_M.gguf -t misra-smart-fixer:latest -f Dockerfile_GPU .
    ```

    Build the Docker image with CPU support, passing the local model file as a build argument.
    ```sh
    sudo DOCKER_BUILDKIT=1 docker build --build-arg MODEL_FILE=./codellama-7b-instruct.Q4_K_M.gguf -t misra-smart-fixer:latest -f Dockerfile_CPU .
    ```

5.  **Run the Docker Container:**
    This command runs the container, mapping the container's port 7860 to the host machine's port 7860. The first time you run this, it will take some time to load the model.
    ```sh
    sudo docker run --rm --gpus all -v "$(pwd)":/workspace -p 7860:7860 misra-smart-fixer:latest
    ```
    You should see logs similar to:
    ```
    Model loaded successfully with GPU acceleration.
    ...
    * Running on local URL:  [http://0.0.0.0:7860](http://0.0.0.0:7860)
    ```
    For CPU mode,
    ```sh
    sudo docker run --rm -v "$(pwd)":/workspace -p 7860:7860 misra-smart-fixer:latest
    ```
    You should see logs similar to:
    ```
    * Running on local URL:  [http://0.0.0.0:7860](http://0.0.0.0:7860)
    ```

6.  **Access the Web UI:**
    On your host PC (or in your native Linux OS), open your web browser and navigate to:
    [http://127.0.0.1:7860](http://127.0.0.1:7860)


<img width="1640" height="548" alt="UI interface" src="https://github.com/user-attachments/assets/27d1b1fd-ee2a-4da4-8074-04e17390f39a" />

**UI shows predictive patch:**

<img width="1628" height="572" alt="Prediction" src="https://github.com/user-attachments/assets/832f7a6f-4ff0-4b83-910b-457498330cc4" />

