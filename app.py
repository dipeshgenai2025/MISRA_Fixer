# ==============================================================================
# File: app.py
#
# Description: This script provides a web-based interface for a MISRA-C/C++
#              violation fixer. It uses a local instance of cppcheck for static
#              analysis and a local LLM (Llama CPP) to generate code patches.
#
# Author: Dipesh Karmakar
#
# This source code is licensed under the MIT License. See the LICENSE file in the
# project root for the full license text.
#
# Version: 1.1
# ==============================================================================

import os
import json
import subprocess
import gradio as gr
import wandb
import shutil
import sys
import xml.etree.ElementTree as ET
import tempfile
from llama_cpp import Llama

# 1. Initialize W&B (free tier) for basic logging
# This is useful for tracking application usage and model performance.
key = os.getenv("WANDB_API_KEY")
if key:
    wandb.login(key=key, relogin=True)

try:
    wandb.init(
        project="misra-smart-fixer",
        mode="online",
        anonymous="must"
    )
except Exception as e:
    print(f"Warning: Failed to initialize wandb. {e}", file=sys.stderr)

# 2. Local Model Setup
# IMPORTANT: The model path now points to the file copied in the Dockerfile.
LOCAL_MODEL_PATH = "/app/codellama-7b-instruct.Q4_K_M.gguf"

if not os.path.exists(LOCAL_MODEL_PATH):
    print(f"Error: Local model path '{LOCAL_MODEL_PATH}' not found.", file=sys.stderr)
    print("Please ensure the model file is copied into the container.", file=sys.stderr)
    sys.exit(1)

# Initialize the Llama CPP client with the local GGUF model.
try:
    print(f"Loading local model from {LOCAL_MODEL_PATH}...")
    # The Llama class from llama-cpp-python is used to load and run GGUF models.
    # The 'n_gpu_layers' parameter offloads model layers to the GPU for faster inference.
    # This value should be adjusted based on the available VRAM.
    llm = Llama(
        model_path=LOCAL_MODEL_PATH,
        n_ctx=2048, # The maximum context size
        n_gpu_layers=40 # Set to -1 for all layers, or a positive number.
    )
    print("Model loaded successfully with GPU acceleration.")
except Exception as e:
    print(f"Error loading local model: {e}", file=sys.stderr)
    sys.exit(1)

def ensure_tool(name: str):
    """
    Checks if a command-line tool is available in the system's PATH.

    Args:
        name (str): The name of the tool to check for.
    """
    if shutil.which(name) is None:
        print(f"Error: `{name}` not found. Please install it and retry.", file=sys.stderr)
        sys.exit(1)

def run_cppcheck(source_code: str, filename: str) -> list:
    """
    Runs cppcheck on the provided source code and parses the XML output for issues.
    
    This function has been optimized to use temporary files from the `tempfile`
    module, which is more secure and automatically handles cleanup.
    
    Args:
        source_code (str): The content of the source file.
        filename (str): The name of the source file, used to determine the language.
        
    Returns:
        list: A list of dictionaries, where each dictionary represents a detected issue.
    """
    ensure_tool("cppcheck")
    
    issues = []

    # Use a temporary file for the source code, which is automatically cleaned up.
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.c', encoding='utf-8') as src_file, \
         tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.xml', encoding='utf-8') as xml_file:
        
        src_file_path = src_file.name
        xml_file_path = xml_file.name
        
        src_file.write(source_code)
        src_file.flush() # Ensure all data is written to the file
        
        # Select language and standard based on the file extension.
        if filename.endswith(".c"):
            lang_args = ["--std=c99", "--language=c", "--addon=misra"]
        else:
            lang_args = ["--std=c++17", "--language=c++", "--profile=misra-cpp-2012"]

        # Construct and run the cppcheck command.
        cmd = ["cppcheck", "--enable=all", "--xml", *lang_args, src_file_path]
        try:
            # Redirect stderr to the temporary XML file.
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=xml_file, text=True, encoding='utf-8')

            # Rewind the XML file and parse its contents.
            xml_file.seek(0)
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Extract issue information from the XML.
            for error_element in root.findall(".//error"):
                location = error_element.find('location')
                if location is not None:
                    issue = {
                        "severity": error_element.get('severity'),
                        "id": error_element.get('id'),
                        "msg": error_element.get('msg'),
                        "verbose": error_element.get('verbose'),
                        "file": location.get('file'),
                        "line": location.get('line'),
                        "column": location.get('column')
                    }
                    issues.append(issue)

        except (subprocess.CalledProcessError, ET.ParseError) as e:
            print(f"An error occurred during cppcheck execution or XML parsing: {e}", file=sys.stderr)
            # Read the raw output for debugging
            xml_file.seek(0)
            print(f"Raw cppcheck XML output:\n{xml_file.read()}", file=sys.stderr)
            
    # The temporary files are automatically deleted here
    return issues

def build_prompt(source_code: str, filename: str, issues: list) -> str:
    """
    Builds the prompt for the language model based on the parsed issues.
    The prompt is formatted for CodeLlama Instruct models to generate a patch.
    
    Args:
        source_code (str): The original source code.
        filename (str): The name of the file.
        issues (list): A list of dictionaries representing the detected issues.
        
    Returns:
        str: The formatted prompt string, or None if there are no issues.
    """
    if not issues:
        return None

    # Create a summary of the issues to be included in the prompt.
    summary = "\n".join([
        f"- {issue['file']}:{issue['line']}:{issue['column']} {issue['severity']}: {issue['msg']} ({issue['id']})"
        for issue in issues
    ])

    rule_set = "MISRA C:2012" if filename.endswith(".c") else "MISRA C++:2012"
    
    # Use the specific instruct format for CodeLlama models.
    prompt_template = f"""
[INST] You are a { 'C expert' if 'C:2012' in rule_set else 'C++ expert' } specializing in {rule_set} compliance.
Here is the source file:
```
{source_code}
```
The static analyzer reported the following violations:
{summary}
Produce a unified diff patch that fixes all violations. For each change, include a one‐sentence rationale referencing the violated rule number.
Only return the diff. No extra commentary. [/INST]
"""
    return prompt_template.strip()

def predict_patch(prompt: str) -> str:
    """
    Calls the local Llama model to generate a patch based on the prompt.
    
    Args:
        prompt (str): The formatted prompt string for the LLM.
        
    Returns:
        str: The generated patch string.
    """
    try:
        # Call the Llama instance with the prompt to get the patch.
        response = llm(
            prompt,
            max_tokens=512, # Adjust max_tokens as needed for a longer patch.
            stop=["[INST]"], # Stop generation when it hits the instruction token.
            echo=False # Do not include the prompt in the output.
        )
        
        # Extract the text from the LLM's response.
        patch = response["choices"][0]["text"]
        wandb.log({"prompt": prompt, "patch": patch})
        return patch
    except Exception as e:
        print(f"Error during local model inference: {e}", file=sys.stderr)
        raise e

def process_file(file_obj) -> tuple:
    """
    Main function to process an uploaded file.
    It orchestrates the entire workflow: file reading, analysis, prompt building, and patch generation.
    
    This version includes a fix to handle cases where file_obj is a string path
    instead of a file-like object, which can occur with some Gradio versions.
    
    Args:
        file_obj: The file object uploaded via the Gradio interface.
        
    Returns:
        tuple: A tuple containing the result message and the generated patch (or None).
    """
    if file_obj is None:
        return "Error: No file uploaded.", None

    filename = file_obj.name
    
    try:
        # Check if the input is a string (a file path) or a file-like object.
        if isinstance(file_obj.name, str):
            with open(file_obj.name, 'r', encoding='utf-8') as f:
                src = f.read()
        else:
            file_obj.seek(0)
            src = file_obj.read().decode()
    except Exception as e:
        return f"Failed to read file: {e}", None

    if not src:
        return "Error: The uploaded file appears to be empty.", None

    issues = run_cppcheck(src, filename)
    
    prompt = build_prompt(src, filename, issues)
    if prompt is None:
        return "No MISRA violations found.", None
    
    try:
        patch = predict_patch(prompt)
        return "Patch generated below:", patch
    except Exception as e:
        return f"An error occurred during local model inference: {e}", None

def main():
    """
    Sets up and launches the Gradio interface.
    """
    iface = gr.Interface(
        fn=process_file,
        inputs=gr.File(file_types=[".c", ".cpp", ".h", ".hpp"]),
        outputs=[gr.Text(label="Status"), gr.Code(label="Patch")],
        title="MISRA Smart Fixer",
        description="Upload C/C++ code to auto-fix MISRA violations.",
        allow_flagging="never"
    )
    iface.launch(server_name="0.0.0.0", server_port=7860)

if __name__ == "__main__":
    main()

