import cv2
import pytesseract
import requests
import argparse

# Tesseract path for Apple Silicon
pytesseract.pytesseract.tesseract_cmd = "/opt/homebrew/bin/tesseract"

# LLM service endpoint
LLM_SERVICE_URL = "http://localhost:8001/analyze"


def preprocess_image(image_path):

    img = cv2.imread(image_path)

    if img is None:
        raise ValueError("Image not found or unsupported format")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]

    return thresh


def run_ocr(image_path):

    processed = preprocess_image(image_path)

    text = pytesseract.image_to_string(processed)

    return text


def send_to_llm(text):

    try:

        response = requests.post(
            LLM_SERVICE_URL,
            json={"text": text},
            timeout=30
        )

        # Check if request succeeded
        if response.status_code != 200:
            return {
                "error": f"LLM service returned status {response.status_code}",
                "details": response.text
            }

        try:
            return response.json()

        except Exception:
            return {
                "error": "Invalid JSON returned from LLM service",
                "details": response.text
            }

    except Exception as e:

        return {
            "error": "Failed to connect to LLM service",
            "details": str(e)
        }


def main():

    parser = argparse.ArgumentParser(
        description="OCR Client for Medical Report Analysis"
    )

    parser.add_argument(
        "-i",
        "--image",
        required=True,
        help="Path to report image"
    )

    args = parser.parse_args()

    print("\nRunning OCR...\n")

    ocr_text = run_ocr(args.image)

    print("----- OCR TEXT -----\n")

    print(ocr_text)

    print("\nSending to LLM service...\n")

    result = send_to_llm(ocr_text)

    print("\n----- AI ANALYSIS -----\n")

    if "analysis" in result:
        print(result["analysis"])
    else:
        print("LLM SERVICE ERROR:\n")
        print(result)


if __name__ == "__main__":
    main()