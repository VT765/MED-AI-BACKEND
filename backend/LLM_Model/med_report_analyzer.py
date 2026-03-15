#!/usr/bin/env python3

import argparse
import cv2
import pytesseract
import requests
import json
import sys

# Tesseract path for Apple Silicon
pytesseract.pytesseract.tesseract_cmd = "/opt/homebrew/bin/tesseract"


# -----------------------------
# IMAGE PREPROCESSING
# -----------------------------
def preprocess_image(image_path):

    img = cv2.imread(image_path)

    if img is None:
        raise ValueError("Image not found or unsupported format")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]

    return thresh


# -----------------------------
# OCR FUNCTION
# -----------------------------
def run_ocr(image_path):

    processed = preprocess_image(image_path)

    text = pytesseract.image_to_string(processed)

    return text


# -----------------------------
# AI ANALYSIS FUNCTION
# -----------------------------
def analyze_report(text, model="llama3.2:3b"):

    prompt = f"""
You are a medical AI assistant.

Analyze the following OCR extracted medical report.

Tasks:
1. Extract patient details
2. Identify diagnosis
3. Detect abnormal findings
4. Summarize health condition
5. Suggest if medical attention is needed

Medical Report:
{text}

Return a structured explanation.
"""

    try:

        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False
            }
        )

        data = response.json()

        if "response" in data:
            return data["response"]

        else:
            print("\n⚠ Ollama returned unexpected response:\n")
            print(json.dumps(data, indent=2))
            return "Model failed to generate analysis."

    except Exception as e:

        print("\n❌ Error connecting to Ollama server\n")
        print(e)
        print("\nMake sure Ollama server is running:\n")
        print("ollama serve")

        sys.exit(1)


# -----------------------------
# MAIN PIPELINE
# -----------------------------
def main():

    parser = argparse.ArgumentParser(description="Med-AI Medical Report Analyzer")

    parser.add_argument(
        "-i",
        "--image",
        required=True,
        help="Path to medical report image"
    )

    parser.add_argument(
        "-m",
        "--model",
        default="llama3.2:3b",
        help="Ollama model name"
    )

    args = parser.parse_args()

    print("\n🔍 Running OCR...\n")

    ocr_text = run_ocr(args.image)

    print("------ OCR TEXT ------\n")

    print(ocr_text)

    print("\n🧠 Running AI Medical Analysis...\n")

    analysis = analyze_report(ocr_text, args.model)

    print("------ AI ANALYSIS ------\n")

    print(analysis)


if __name__ == "__main__":
    main()