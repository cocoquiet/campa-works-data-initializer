import httpx
import json

from scrapper.master_course.master_course import (
    excel_file_path,
    fetch_excel_curriculums,
)

curriculum_url = (
    "https://knuin.knu.ac.kr/public/web/stddm/curse/educourse/eduCour/searchEduCourList"
)

years = range(2020, 2027)
SEMESTER_TYPES = {
    "STCU000600001": ["FIRST"],
    "STCU000600002": ["SECOND"],
    "STCU000600003": ["FIRST", "SECOND"],
}
GRADUATE_SEMESTERS = ("FIRST", "SECOND")
COURSE_CATEGORIES = {
    "STCU000700001": "MAJOR",
    "STCU000700002": "TEACHER_EDUCATION",
    "STCU000700003": "GENERAL_ELECTIVE",
    "STCU000700004": "FREE_ELECTIVE",
}
EXCEL_COURSE_CATEGORIES = {
    "전공필수": "MAJOR_REQUIRED",
    "전공": "MAJOR_ELECTIVE",
    "교직": "TEACHER_EDUCATION",
    "교양": "GENERAL_ELECTIVE",
    "자유선택": "FREE_ELECTIVE",
}

request_payload = {
    "isApi": "Y",
    "search": {
        "dprtnCd": "",
        "dprtnNm": "",
        "forMdlMgmntYn": "Y",
        "frstNcrYear": 2026,
        "isApi": "Y",
        "mdlSctinCd": "STCU001800001",
        "trgtYrsf": 0,
    },
}


def fetch_course_curriculums(major_code, year):
    request_payload["search"]["dprtnCd"] = major_code
    request_payload["search"]["trgtYrsf"] = year

    response = httpx.post(
        curriculum_url,
        json=request_payload,
        timeout=20.0,
    )

    if response.status_code == 200:
        return json.loads(response.text)["data"]
    else:
        print(
            f"Failed to fetch the main page. Status code: {response.status_code}, Message: {response.text}"
        )
        return []


def post_single_course_curriculum(data: dict) -> bool:
    response = httpx.post(
        "http://localhost:8080/api/course-curriculums",
        json=data,
    )

    if response.status_code != 201:
        print(
            f"Failed to post course curriculum data for {data}. "
            f"Status code: {response.status_code}, Message: {response.text}"
        )
    else:
        print(f"Successfully posted data for {data}.")

    return response.status_code in [201, 409]


def get_course_curriculum_targets(major_code, record):
    if str(major_code).startswith("2"):
        return [(semester, 1) for semester in GRADUATE_SEMESTERS]

    semester_types = SEMESTER_TYPES.get(record.get("estblSmstrCd"))
    grade_value = record.get("estblGrade")
    if semester_types is None or grade_value is None:
        return []

    try:
        grade = int(grade_value)
    except TypeError, ValueError:
        return []

    if grade not in range(1, 5):
        return []

    return [(semester, grade) for semester in semester_types]


def post_excel_course_curriculums():
    majors = httpx.get("http://localhost:8080/api/majors").json()
    master_courses = httpx.get("http://localhost:8080/api/master-courses").json()
    curriculums = httpx.get("http://localhost:8080/api/curriculums").json()

    master_course_ids = {}
    for course in master_courses:
        master_course_ids.setdefault(course["course_code"], []).append(course["id"])

    curriculum_ids = {}
    for curriculum in curriculums:
        key = (
            curriculum["major"]["id"],
            curriculum["semester"]["year"],
            curriculum["semester"]["semester_"],
            curriculum["grade"],
        )
        curriculum_ids.setdefault(key, []).append(curriculum["id"])

    posted = set()
    records = fetch_excel_curriculums(excel_file_path)

    for record in records:
        matching_majors = [
            major for major in majors if major["major_code"] == record["major_code"]
        ]

        if len(matching_majors) != 1:
            print(
                f"Failed to post course curriculum data for {record['course_code']}. No matching major found."
            )
            continue

        course_ids = master_course_ids.get(record["course_code"], [])

        matching_curriculum_ids = curriculum_ids.get(
            (
                matching_majors[0]["id"],
                record["year"],
                record["semester_"],
                record["grade"],
            ),
            [],
        )

        if len(course_ids) != 1 or len(matching_curriculum_ids) != 1:
            print(
                f"Failed to post course curriculum data for {record['course_code']}. No matching course or curriculum found."
            )
            continue

        course_category = EXCEL_COURSE_CATEGORIES.get(record["category"])
        if course_category is None:
            print(
                f"Failed to post course curriculum data for {record['course_code']}. "
                f"Unknown course category: {record['category']!r}."
            )
            continue

        data = {
            "master_course_id": course_ids[0],
            "curriculum_id": matching_curriculum_ids[0],
            "course_category": course_category,
        }

        connection = (
            data["master_course_id"],
            data["curriculum_id"],
        )

        if connection in posted:
            continue
        if post_single_course_curriculum(data):
            posted.add(connection)


def post_scraped_course_curriculums(
    major,
    records,
    source_year,
    target_year,
    master_course_ids,
    curriculum_ids,
    posted,
):
    for record in records:
        if (
            str(record.get("dprtnCd")) != str(major["major_code"])
            or int(record.get("trgtYrsf")) != source_year
        ):
            continue

        curriculum_targets = get_course_curriculum_targets(major["major_code"], record)
        if not curriculum_targets:
            continue

        course_code = record.get("sbjetCd")
        course_ids = master_course_ids.get(course_code, [])
        if len(course_ids) != 1:
            print(
                f"Failed to post course curriculum data for {course_code}. "
                "No matching course found."
            )
            continue

        course_category = COURSE_CATEGORIES.get(record.get("sbjetSctinClscd"))
        if course_category is None:
            print(
                f"Failed to post course curriculum data for {course_code}. "
                "Unknown course type."
            )
            continue
        if course_category == "MAJOR":
            if record.get("sbjetSctcd") == "STCU000800012":
                course_category = "MAJOR_REQUIRED"
            elif record.get("sbjetSctcd") == "STCU000800004":
                course_category = "MAJOR_ELECTIVE"
            else:
                print(
                    f"Failed to post course curriculum data for {course_code}. "
                    "Unknown major course type."
                )
                continue

        for semester_type, grade in curriculum_targets:
            matching_curriculum_ids = curriculum_ids.get(
                (major["id"], target_year, semester_type, grade),
                [],
            )

            if len(matching_curriculum_ids) != 1:
                print(
                    f"Failed to post course curriculum data for {course_code}. "
                    f"No matching curriculum found for {target_year}."
                )
                continue

            data = {
                "master_course_id": course_ids[0],
                "curriculum_id": matching_curriculum_ids[0],
                "course_category": course_category,
            }

            connection = (
                data["master_course_id"],
                data["curriculum_id"],
            )

            if connection in posted:
                continue

            if post_single_course_curriculum(data):
                posted.add(connection)


def post_course_curriculums():
    major_response = httpx.get("http://localhost:8080/api/majors")
    major_response.raise_for_status()
    majors = major_response.json()

    course_response = httpx.get("http://localhost:8080/api/master-courses")
    course_response.raise_for_status()
    master_courses = course_response.json()

    curriculum_response = httpx.get("http://localhost:8080/api/curriculums")
    curriculum_response.raise_for_status()
    curriculums = curriculum_response.json()

    master_course_ids = {}
    for course in master_courses:
        master_course_ids.setdefault(course["course_code"], []).append(course["id"])

    curriculum_ids = {}
    for curriculum in curriculums:
        key = (
            curriculum["major"]["id"],
            curriculum["semester"]["year"],
            curriculum["semester"]["semester_"],
            curriculum["grade"],
        )
        curriculum_ids.setdefault(key, []).append(curriculum["id"])

    posted = set()

    for major in majors:
        print(f"\nProcessing {major['major_name']}({major['major_code']})...")

        for year in years:
            try:
                records = fetch_course_curriculums(
                    major["major_code"],
                    year,
                )
                post_scraped_course_curriculums(
                    major,
                    records,
                    source_year=year,
                    target_year=year,
                    master_course_ids=master_course_ids,
                    curriculum_ids=curriculum_ids,
                    posted=posted,
                )

                if str(major["major_code"]).startswith("2") and year == 2026:
                    post_scraped_course_curriculums(
                        major,
                        records,
                        source_year=2026,
                        target_year=2027,
                        master_course_ids=master_course_ids,
                        curriculum_ids=curriculum_ids,
                        posted=posted,
                    )

            except Exception as e:
                print(f"An error occurred for year {year}: {e}")

    post_excel_course_curriculums()


if __name__ == "__main__":
    post_course_curriculums()
