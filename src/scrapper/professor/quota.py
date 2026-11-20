"""Register 2027 first- and second-semester professor quotas from the survey."""

from __future__ import annotations

import argparse
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx
import openpyxl
from dotenv import load_dotenv


PROJECT_PATH = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_PATH / ".env")
_configured_file = os.getenv("PROFESSOR_FILE_PATH")
DEFAULT_EXCEL_FILE = (
    (PROJECT_PATH / _configured_file).expanduser()
    if _configured_file
    else Path.home()
    / "Downloads"
    / "2027학년도_교수님별_희망교과목_설문응답_정제완료.xlsx"
)
DEFAULT_API_BASE_URL = "http://localhost:8080"
QUOTA_COLUMNS = {
    "FIRST": "1학기 책임시수",
    "SECOND": "2학기 책임시수",
}
NON_TEACHING_MARKERS = ("연구년", "명예교수")
NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _find_column(headers: tuple, prefix: str) -> int:
    for index, value in enumerate(headers):
        if _text(value).startswith(prefix):
            return index
    raise ValueError(f"Required Excel column not found: {prefix}")


def _parse_quota(raw_value: object, professor_name: str, semester: str) -> dict | None:
    value = _text(raw_value)
    if not value or value in {"-", "."}:
        return None

    quota_type = "HOUR" if "시간" in value else "CREDIT"
    if any(marker in value for marker in NON_TEACHING_MARKERS):
        unit_match = re.search(r"-?\d+(?:\.\d+)?\s*(학점|시간)", value)
        if not unit_match:
            return {"quota_type": quota_type, "quota_value": 0}
        quota_type = "HOUR" if unit_match.group(1) == "시간" else "CREDIT"
        value = value[unit_match.start() :]

    # For explanatory answers, use the explicitly stated actual load when present.
    actual_index = value.rfind("실제로")
    if actual_index >= 0:
        value = value[actual_index:]

    match = NUMBER_PATTERN.search(value)
    if not match:
        print(
            f"Skipping {professor_name} {semester}: "
            f"could not parse quota value {raw_value!r}."
        )
        return None

    try:
        quota = Decimal(match.group())
    except InvalidOperation:
        print(
            f"Skipping {professor_name} {semester}: "
            f"invalid quota value {raw_value!r}."
        )
        return None

    if quota != quota.to_integral_value():
        print(
            f"Skipping {professor_name} {semester}: {quota} cannot be stored "
            "because professor_quota.quota_value is an integer."
        )
        return None

    return {"quota_type": quota_type, "quota_value": int(quota)}


def fetch_excel_quotas(excel_file_path: Path) -> list[dict]:
    if not excel_file_path.is_file():
        raise FileNotFoundError(f"Excel file not found: {excel_file_path}")

    workbook = openpyxl.load_workbook(
        excel_file_path,
        data_only=True,
        read_only=True,
    )
    try:
        sheet = workbook.active
        headers = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
        email_column = _find_column(headers, "이메일 주소")
        first_column = _find_column(headers, QUOTA_COLUMNS["FIRST"])
        second_column = _find_column(headers, QUOTA_COLUMNS["SECOND"])
        name_column = _find_column(headers, "이름")

        # The workbook has repeated submissions; retain the last row per email.
        rows_by_email: dict[str, dict] = {}
        for row in sheet.iter_rows(min_row=2, values_only=True):
            email = _text(row[email_column])
            name = _text(row[name_column])
            if not email or not name:
                continue
            rows_by_email[email.casefold()] = {
                "email": email,
                "name": name,
                "first_quota": row[first_column],
                "second_quota": row[second_column],
            }

        quota_rows = []
        for record in rows_by_email.values():
            for semester_key, field in (
                ("FIRST", "first_quota"),
                ("SECOND", "second_quota"),
            ):
                quota = _parse_quota(
                    record[field],
                    record["name"],
                    semester_key,
                )
                if quota is None:
                    continue
                quota_rows.append(
                    {
                        "email": record["email"],
                        "name": record["name"],
                        "semester_key": semester_key,
                        **quota,
                    }
                )
        return quota_rows
    finally:
        workbook.close()


def post_excel_professor_quotas(
    excel_file_path: Path,
    api_base_url: str,
) -> None:
    quota_rows = fetch_excel_quotas(excel_file_path)
    print(f"Prepared {len(quota_rows)} professor quota records.")

    with httpx.Client(timeout=20.0) as client:
        semesters_response = client.get(f"{api_base_url}/api/semesters")
        semesters_response.raise_for_status()
        semester_ids = {
            (semester["year"], semester["semester_"]): semester["id"]
            for semester in semesters_response.json()
        }

        semester_id_by_key = {}
        for semester_key in ("FIRST", "SECOND"):
            semester_id = semester_ids.get((2027, semester_key))
            if semester_id is None:
                raise ValueError(
                    f"2027 {semester_key} semester was not found via /api/semesters."
                )
            semester_id_by_key[semester_key] = semester_id

        professors_response = client.get(f"{api_base_url}/api/professors")
        professors_response.raise_for_status()
        professor_ids_by_email = {
            professor["user"]["email"].casefold(): professor["id"]
            for professor in professors_response.json()
        }

        quotas_response = client.get(f"{api_base_url}/api/professor-quotas")
        quotas_response.raise_for_status()
        existing_quota_keys = {
            (quota["professor"]["id"], quota["semester"]["id"])
            for quota in quotas_response.json()
        }

        created = 0
        skipped_existing = 0
        skipped_missing_professor = 0
        for quota in quota_rows:
            professor_id = professor_ids_by_email.get(quota["email"].casefold())
            if professor_id is None:
                print(
                    f"Skipping {quota['name']}: no professor record for "
                    f"{quota['email']}."
                )
                skipped_missing_professor += 1
                continue

            semester_id = semester_id_by_key[quota["semester_key"]]
            key = (professor_id, semester_id)
            if key in existing_quota_keys:
                print(
                    f"Skipping existing quota for {quota['name']} "
                    f"({quota['semester_key']})."
                )
                skipped_existing += 1
                continue

            payload = {
                "professor_id": professor_id,
                "semester_id": semester_id,
                "quota_type": quota["quota_type"],
                "quota_value": quota["quota_value"],
            }
            response = client.post(
                f"{api_base_url}/api/professor-quotas",
                json=payload,
            )
            if response.status_code != 201:
                print(
                    f"Failed to post quota for {quota['name']} "
                    f"({quota['semester_key']}). Status code: "
                    f"{response.status_code}, Message: {response.text}"
                )
                continue

            created += 1
            existing_quota_keys.add(key)
            print(
                f"Created {quota['semester_key']} quota for {quota['name']}: "
                f"{quota['quota_value']} {quota['quota_type']}."
            )

    print(
        f"Finished: created={created}, existing={skipped_existing}, "
        f"missing_professor={skipped_missing_professor}."
    )


def post_quotas() -> None:
    parser = argparse.ArgumentParser(
        description="Register 2027 first- and second-semester professor quotas."
    )
    parser.add_argument(
        "excel_file",
        nargs="?",
        type=Path,
        default=DEFAULT_EXCEL_FILE,
        help=f"workbook path (default: {DEFAULT_EXCEL_FILE})",
    )
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help=f"API base URL (default: {DEFAULT_API_BASE_URL})",
    )
    args = parser.parse_args()
    post_excel_professor_quotas(args.excel_file, args.api_base_url.rstrip("/"))


if __name__ == "__main__":
    post_quotas()
