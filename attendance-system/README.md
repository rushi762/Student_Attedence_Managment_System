# Student Attendance Management System

Flask + SQLite app with **separate Student and Teacher portals**.

## Features
**Student portal** – register / login, profile with overall % and subject-wise attendance,
day-wise view per subject, download attendance sheet (CSV, opens in Excel).

**Teacher portal** – register / login (each teacher is linked to a subject), mark attendance
by class and date, **edit only on the same day (locked after 11:59 PM IST)**, view students
and open any student's profile (attendance in every subject), dashboard with low-attendance
list, download class attendance sheet (date-wise P/A matrix with percentages).

Students under 75% are highlighted in red.

## Default data (created on first run)
- 10 teachers `T01`–`T10`, password `teacher123` (one subject each)
- 20 students `S001`–`S020`, password `student123` (CSE-A and CSE-B)
- About 3 weeks of sample attendance so reports are not empty

## Run
```bash
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000. To reset all data, stop the app and delete `college.db`.

Set the `SECRET_KEY` environment variable and change the default passwords before
deploying anywhere public.
