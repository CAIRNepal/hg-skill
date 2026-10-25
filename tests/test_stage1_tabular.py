import json
import csv
import sys
from pathlib import Path
import pytest
import openpyxl

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skills" / "01_heritage-extract" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from ingest_tabular import (
    ingest_csv,
    ingest_excel,
    ingest_json,
    clean_record,
    categorize_fields
)


def test_clean_record():
    raw = {
        "name": "Nyatapola ",
        "empty": "",
        "na": "N/A",
        "null_val": "null",
        "valid_num": 108,
        "valid_desc": " A five-tiered temple "
    }
    cleaned = clean_record(raw)
    assert cleaned == {
        "name": "Nyatapola",
        "valid_num": 108,
        "valid_desc": "A five-tiered temple"
    }


def test_categorize_fields():
    fields = ["id", "monument_name", "latitude", "longitude", "description_en", "history_text", "district", "descendants"]
    structured, narrative = categorize_fields(fields)
    assert "id" in structured
    assert "latitude" in structured
    assert "longitude" in structured
    assert "district" in structured
    assert "descendants" in structured
    assert "description_en" in narrative
    assert "history_text" in narrative


def test_ingest_csv_latin1(tmp_path):
    csv_file = tmp_path / "latin1.csv"
    with open(csv_file, "wb") as f:
        f.write("id,name,description\nm1,Café,Ancient site\n".encode("latin-1"))

    records, metadata = ingest_csv(csv_file)
    assert len(records) == 1
    assert records[0]["structured"]["name"] == "Café"



def test_ingest_csv(tmp_path):
    csv_file = tmp_path / "monuments.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "district", "description"])
        writer.writeheader()
        writer.writerow({
            "id": "mon-001",
            "name": "Nyatapola Temple",
            "district": "Bhaktapur",
            "description": "Built in 1702 CE by King Bhupatindra Malla."
        })
        writer.writerow({
            "id": "mon-002",
            "name": "Bhairavnath Temple",
            "district": "Bhaktapur",
            "description": "Dedicated to Kashi Bhairav."
        })

    records, metadata = ingest_csv(csv_file)
    assert len(records) == 2
    assert records[0]["id"] == "mon-001"
    assert records[0]["structured"]["district"] == "Bhaktapur"
    assert "Bhupatindra Malla" in records[0]["narrative"]["description"]
    assert metadata["format"] == "csv"
    assert metadata["record_count"] == 2


def test_ingest_excel(tmp_path):
    xlsx_file = tmp_path / "monuments.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Monuments"
    ws.append(["id", "name", "latitude", "description"])
    ws.append(["mon-101", "Changu Narayan", 27.716, "Ancient Vishnu temple on ridge."])
    wb.save(xlsx_file)

    records, metadata = ingest_excel(xlsx_file)
    assert len(records) == 1
    assert records[0]["id"] == "mon-101"
    assert records[0]["structured"]["latitude"] == 27.716
    assert "Ancient Vishnu" in records[0]["narrative"]["description"]
    assert metadata["format"] == "xlsx"


def test_ingest_json(tmp_path):
    json_file = tmp_path / "catalog.json"
    data = [
        {
            "accession_no": "ACC-001",
            "title": "Dipankara Buddha Statue",
            "material": "Gilt copper alloy",
            "description": "Repousse sculpture from Patan."
        }
    ]
    json_file.write_text(json.dumps(data), encoding="utf-8")

    records, metadata = ingest_json(json_file)
    assert len(records) == 1
    assert records[0]["structured"]["accession_no"] == "ACC-001"
    assert "Patan" in records[0]["narrative"]["description"]
    assert metadata["format"] == "json"
