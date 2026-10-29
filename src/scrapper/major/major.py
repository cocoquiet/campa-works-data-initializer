import httpx
from bs4 import BeautifulSoup


def post_majors():
    majors = [
        {"major_name": "컴퓨터학부", "major_code": "1O02", "major_status": "ACTIVE"},
        {
            "major_name": "글로벌소프트웨어융합전공",
            "major_code": "1O0204",
            "major_status": "ACTIVE",
        },
        {
            "major_name": "플랫폼소프트웨어전공",
            "major_code": "1O0205",
            "major_status": "ACTIVE",
        },
        {
            "major_name": "데이터과학전공",
            "major_code": "1O0206",
            "major_status": "ACTIVE",
        },
        {
            "major_name": "인공지능컴퓨팅전공",
            "major_code": "1O0208",
            "major_status": "ACTIVE",
        },
        {
            "major_name": "심화컴퓨팅전공",
            "major_code": "1O0209",
            "major_status": "ACTIVE",
        },
        {
            "major_name": "첨단컴퓨팅연구전공",
            "major_code": "1O0210",
            "major_status": "ACTIVE",
        },
        {"major_name": "ICT융합학과", "major_code": "1O15", "major_status": "ACTIVE"},
        {"major_name": "AI대학", "major_code": "A7", "major_status": "ACTIVE"},
        {
            "major_name": "인공지능시스템학과",
            "major_code": "A701",
            "major_status": "ACTIVE",
        },
        {"major_name": "컴퓨터학부", "major_code": "A702", "major_status": "ACTIVE"},
        {
            "major_name": "심화컴퓨팅전공",
            "major_code": "A70201",
            "major_status": "ACTIVE",
        },
        {
            "major_name": "첨단AI컴퓨팅전공",
            "major_code": "A70202",
            "major_status": "ACTIVE",
        },
        {
            "major_name": "플랫폼소프트웨어전랫",
            "major_code": "A70203",
            "major_status": "ACTIVE",
        },
        {
            "major_name": "데이터과학전공",
            "major_code": "A70204",
            "major_status": "ACTIVE",
        },
        {"major_name": "AI자율학부", "major_code": "A703", "major_status": "ACTIVE"},
        {"major_name": "컴퓨터학부", "major_code": "21153", "major_status": "ACTIVE"},
        {
            "major_name": "ICT융합전공",
            "major_code": "2115302",
            "major_status": "ACTIVE",
        },
        {
            "major_name": "디지털융합전공",
            "major_code": "2115303",
            "major_status": "ACTIVE",
        },
        {
            "major_name": "정보과학과",
            "major_code": "21168",
            "major_status": "ACTIVE",
        },
        {
            "major_name": "데이터융합컴퓨팅학과",
            "major_code": "21180",
            "major_status": "ACTIVE",
        },
        {
            "major_name": "ABB융합전공",
            "major_code": "211A2",
            "major_status": "ACTIVE",
        },
        {
            "major_name": "정보보호학과",
            "major_code": "2111U",
            "major_status": "ACTIVE",
        },
        {
            "major_name": "컴퓨터공학전공",
            "major_code": "2260108",
            "major_status": "ACTIVE",
        }
    ]

    for major in majors:
        response = httpx.post(
            "http://localhost:8080/api/majors",
            json=major,
        )
        if response.status_code != 201:
            print(
                f"Failed to post major data for {major}. Status code: {response.status_code}"
            )
        else:
            print(f"Successfully posted data for {major}.")


if __name__ == "__main__":
    post_majors()
