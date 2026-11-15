"""
Download a Kaggle dataset that contains PDF reports.
1) Create a Kaggle API token: Kaggle -> Settings -> API -> Create New Token.
2) Put kaggle.json in ~/.kaggle/kaggle.json (Windows: C:\\Users\\<you>\\.kaggle\\kaggle.json).
3) Run: python download_kaggle_dataset.py --dataset owner/dataset-slug
The script extracts PDFs into data/kaggle_pdfs/.
"""
import argparse, os, shutil
from pathlib import Path
from kaggle.api.kaggle_api_extended import KaggleApi

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="Kaggle dataset slug: owner/dataset-name")
    args = parser.parse_args()
    out = Path("data/kaggle_download")
    out.mkdir(parents=True, exist_ok=True)
    api = KaggleApi()
    api.authenticate()
    api.dataset_download_files(args.dataset, path=str(out), unzip=True, quiet=False)
    pdfs = list(out.rglob("*.pdf")) + list(out.rglob("*.PDF"))
    target = Path("data/kaggle_pdfs")
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    for pdf in pdfs:
        dest = target / pdf.name
        if not dest.exists():
            shutil.copy2(pdf, dest)
            copied += 1
    print(f"Found {len(pdfs)} PDF file(s); copied {copied} new PDF(s) to {target.resolve()}")
    if not pdfs:
        print("This Kaggle dataset did not contain PDFs. Choose a Kaggle dataset whose files include .pdf reports.")

if __name__ == "__main__":
    main()
