"""Register professors from the cleaned 2027 survey workbook."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import httpx
import openpyxl
from dotenv import load_dotenv

project_path = Path(__file__).resolve().parents[3]
load_dotenv(project_path / ".env")
professor_file_path = os.getenv("PROFESSOR_FILE_PATH")
DEFAULT_EXCEL_FILE = (
    (project_path / professor_file_path).expanduser()
    if professor_file_path
    else Path.home()
    / "Downloads"
    / "2027학년도_교수님별_희망교과목_설문응답_정제완료.xlsx"
)
DEFAULT_API_BASE_URL = "http://localhost:8080"
DEFAULT_PASSWORD = "test_password"
DEFAULT_APPOINTED_AT = 1

NULL_FALLBACKS = {
    "office": "정보 없음",
    "tel": "정보 없음",
    "research_field": "정보 없음",
}


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def fetch_excel_professors(excel_file_path: Path) -> list[dict]:
    """Read professor names and emails, keeping the last row for each email."""
    if not excel_file_path.is_file():
        raise FileNotFoundError(f"Excel file not found: {excel_file_path}")

    workbook = openpyxl.load_workbook(
        excel_file_path,
        data_only=True,
        read_only=True,
    )
    try:
        sheet = workbook.active
        header = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
        columns = {_text(value): index for index, value in enumerate(header) if value}

        required_headers = ("이메일 주소", "이름")
        missing_headers = [name for name in required_headers if name not in columns]
        if missing_headers:
            raise ValueError(
                "Required column(s) not found in the first row: "
                + ", ".join(missing_headers)
            )

        professors_by_email: dict[str, dict] = {}
        for row_number, row in enumerate(
            sheet.iter_rows(min_row=2, values_only=True),
            start=2,
        ):
            email = _text(row[columns["이메일 주소"]])
            name = _text(row[columns["이름"]])
            if not email and not name:
                continue
            if not email or not name:
                print(f"Skipping row {row_number}: name or email is missing.")
                continue

            # The workbook contains repeated submissions for some professors.
            professors_by_email[email.casefold()] = {
                "username": name,
                "email": email,
            }

        return list(professors_by_email.values())
    finally:
        workbook.close()


def _post_with_null_fallback(
    client: httpx.Client,
    url: str,
    payload: dict,
    description: str,
) -> httpx.Response:
    response = client.post(url, json=payload)
    if response.status_code in (400, 422):
        fallback_payload = payload.copy()
        null_fields = [
            field
            for field in NULL_FALLBACKS
            if field in fallback_payload and fallback_payload[field] is None
        ]
        error_text = response.text.casefold()
        # Preserve nulls for fields the API did not identify as invalid when possible.
        named_fields = [field for field in null_fields if field.casefold() in error_text]
        fields_to_fill = named_fields or null_fields
        for field in fields_to_fill:
            fallback_payload[field] = NULL_FALLBACKS[field]
        if fields_to_fill:
            # Retry validation failures with placeholders for missing required values.
            response = client.post(url, json=fallback_payload)

    if response.status_code != 201:
        print(
            f"Failed to post {description}. Status code: {response.status_code}, "
            f"Message: {response.text}"
        )
    return response


def post_single_professor(
    client: httpx.Client,
    professor: dict,
    api_base_url: str,
    users_by_email: dict[str, int],
    professor_user_ids: set[int],
) -> bool:
    email_key = professor["email"].casefold()
    user_id = users_by_email.get(email_key)
    if user_id is None:
        user_payload = {
            "username": professor["username"],
            "email": professor["email"],
            "role": "PROFESSOR",
            "password": DEFAULT_PASSWORD,
            "is_super": False,
        }
        user_response = client.post(
            f"{api_base_url}/api/users",
            json=user_payload,
        )
        if user_response.status_code != 201:
            print(
                f"Failed to post user data for {professor['username']}. "
                f"Status code: {user_response.status_code}, "
                f"Message: {user_response.text}"
            )
            return False

        user_id = user_response.json().get("id")
        if user_id is None:
            print(f"User ID was not returned for {professor['username']}.")
            return False
        users_by_email[email_key] = user_id
    else:
        print(f"Reusing existing user for {professor['username']}.")

    if user_id in professor_user_ids:
        print(f"Professor record already exists for {professor['username']}; skipping.")
        return True

    professor_payload = {
        "user_id": user_id,
        "position": "PROFESSOR",
        "office": None,
        "tel": None,
        "research_field": None,
        # The API requires an existing semester ID; the original initializer uses 1.
        "appointed_at": DEFAULT_APPOINTED_AT,
        "professor_status": "ACTIVE",
    }
    professor_response = _post_with_null_fallback(
        client,
        f"{api_base_url}/api/professors",
        professor_payload,
        f"professor data for {professor['username']}",
    )
    if professor_response.status_code == 201:
        professor_user_ids.add(user_id)
        print(f"Successfully posted data for {professor['username']}.")
        return True
    return False


def post_excel_professors(excel_file_path: Path, api_base_url: str) -> None:
    professors = fetch_excel_professors(excel_file_path)
    print(f"Retrieved {len(professors)} unique professors.")

    succeeded = 0
    with httpx.Client(timeout=20.0) as client:
        users_response = client.get(f"{api_base_url}/api/users")
        users_response.raise_for_status()
        users_by_email = {
            user["email"].casefold(): user["id"]
            for user in users_response.json()
        }

        professors_response = client.get(f"{api_base_url}/api/professors")
        professors_response.raise_for_status()
        professor_user_ids = {
            professor_record["user"]["id"]
            for professor_record in professors_response.json()
        }

        for professor in professors:
            if post_single_professor(
                client,
                professor,
                api_base_url,
                users_by_email,
                professor_user_ids,
            ):
                succeeded += 1

    print(f"Finished: {succeeded}/{len(professors)} professors registered.")


def professor_main() -> None:
    parser = argparse.ArgumentParser(
        description="Register professors from the 2027 survey Excel workbook."
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
    post_excel_professors(args.excel_file, args.api_base_url.rstrip("/"))


if __name__ == "__main__":
    professor_main()
