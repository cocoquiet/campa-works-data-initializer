from scrapper.professor import professor, invited, concurrent, visiting
from scrapper.major import major
from scrapper.semester import semester
from scrapper.master_course import master_course
from scrapper.curriculum import curriculum
from scrapper.course_curriculum import course_curriculum


major.post_majors()
semester.post_semesters()
master_course.post_master_courses()
curriculum.post_curriculums()
course_curriculum.post_course_curriculums()
