import httpx
import json
import argparse
import openpyxl
import os
from pathlib import Path
from dotenv import load_dotenv

curriculum_url = (
    "https://knuin.knu.ac.kr/public/web/stddm/curse/educourse/eduCour/searchEduCourList"
)

project_path = Path(__file__).resolve().parents[3]
load_dotenv(project_path / ".env")
excel_file_path = project_path / os.environ["EXCEL_FILE_PATH"]


def fetch_excel_curriculums(excel_file_path):
    major_codes = {
        "인공지능시스템학과": "A701",
        "컴퓨터학부(심화컴퓨팅전공)": "A70201",
        "컴퓨터학부(첨단AI컴퓨팅전공)": "A70202",
    }

    workbook = openpyxl.load_workbook(excel_file_path, data_only=True)
    records = []

    try:
        for sheet_name, major_code in major_codes.items():
            sheet = workbook[sheet_name]

            for row in sheet.iter_rows(min_row=6, max_col=9, values_only=True):
                code, name, en_name, credit, category, grade, term, note = row[1:9]

                if "표준개설" in str(code):
                    break
                if code is None and name is None:
                    continue

                credit, lecture, practice = [
                    int(value.strip().removesuffix("주"))
                    for value in str(credit).strip().split("-")
                ]

                semester_type = {
                    "1학기": "FIRST",
                    "2학기": "SECOND",
                }.get(str(term).strip())
                semesters = [semester_type]

                if "동시개설" in str(note):
                    semesters = ["FIRST", "SECOND"]

                for semester in semesters:
                    records.append(
                        {
                            "major_code": major_code,
                            "year": 2027,
                            "semester_": semester,
                            "grade": int(grade),
                            "course_code": str(code).strip(),
                            "course_name": str(name).strip(),
                            "course_en_name": str(en_name or "").strip(),
                            "credit": credit,
                            "lecture": lecture,
                            "practice": practice,
                        }
                    )
    finally:
        workbook.close()
    return records


def fetch_master_courses(major_code, year):
    request_payload = {
        "isApi": "Y",
        "search": {
            "dprtnCd": major_code,
            "dprtnNm": "",
            "forMdlMgmntYn": "Y",
            "frstNcrYear": 2026,
            "isApi": "Y",
            "mdlSctinCd": "STCU001800001",
            "trgtYrsf": year,
        },
    }

    response = httpx.post(
        curriculum_url,
        json=request_payload,
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json()["data"]


def post_single_master_course(data):
    response = httpx.post(
        "http://localhost:8080/api/master-courses",
        json=data,
        timeout=20.0,
    )
    if response.status_code != 201:
        print(
            f"Failed to post master course for {data.get('course_code')}. "
            f"Status code: {response.status_code}"
        )
    else:
        print(f"Successfully posted data for {data.get('course_code')}.")


def get_course_type(major_code):
    return "GRADUATE" if str(major_code).startswith("2") else "UNDERGRADUATE"


def post_excel_master_courses(excel_file_path):
    records = fetch_excel_curriculums(excel_file_path)

    response = httpx.get("http://localhost:8080/api/master-courses")
    response.raise_for_status()
    course_codes = {course["course_code"] for course in response.json()}

    print(f"Retrieved {len(records)} records.")

    for record in records:
        if record["course_code"] in course_codes:
            continue

        data = {
            "course_code": record["course_code"],
            "course_name": record["course_name"],
            "course_en_name": record["course_en_name"],
            "credit": record["credit"],
            "lecture": record["lecture"],
            "practice": record["practice"],
            "course_type": get_course_type(record["major_code"]),
            "is_core": False,
            "course_status": "ACTIVE",
        }

        response = httpx.post(
            "http://localhost:8080/api/master-courses",
            json=data,
            timeout=20.0,
        )

        if response.status_code != 201:
            print(
                f"Failed to post master course data for "
                f"{record['course_code']}. "
                f"Status code: {response.status_code}"
            )
            response.raise_for_status()
        else:
            print(f"Successfully posted data for {record['course_code']}.")

        course_codes.add(record["course_code"])


def post_master_courses():

    majors = httpx.get("http://localhost:8080/api/majors").json()

    for major in majors:
        print(f"\nProcessing {major['major_name']}({major['major_code']})...")
        for year in range(2020, 2028):
            print(f"  {year}...", end="")
            while True:
                try:
                    data = fetch_master_courses(major["major_code"], year)
                    for record in data:
                        course_code = record["sbjetCd"]
                        course_name = record["sbjetNm"]
                        course_en_name = record["sbjetEnglhNm"]

                        response = httpx.post(
                            "http://localhost:8080/api/master-courses",
                            json={
                                "course_code": course_code,
                                "course_name": course_name,
                                "course_en_name": course_en_name,
                                "credit": int(record["crdit"]),
                                "lecture": int(record["thryTime"]),
                                "practice": int(record["prctsTime"]),
                                "course_type": get_course_type(major["major_code"]),
                                "course_status": "ACTIVE",
                            },
                            headers={"Content-Type": "application/json"},
                        )
                        if response.status_code != 201:
                            print(
                                f"Failed to post master course data for {course_code}. Status code: {response.status_code}"
                            )
                        else:
                            print(f"Successfully posted data for {course_code}.")
                    break
                except httpx.TimeoutException as e:
                    continue
                except Exception as e:
                    print(f"An error occurred for year {year}: {e}")
                    break

    post_excel_master_courses(excel_file_path)


if __name__ == "__main__":
    post_master_courses()
