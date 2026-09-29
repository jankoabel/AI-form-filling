"""Answer sets transcribed from the reference samples vzor1.pdf - vzor3.pdf.

Used by the tests and by ``formfill demo`` to render the three scenarios without a
conversation. Values are given in their already-validated form.
"""

COMMON = {
    "study_level": "bakalárske",
    "academic_year": "2027/2028",
    "method_0": "prezenčná",
    "signature_date": "15.02.2027",
}

VZOR1 = {  # current-year maturant
    **COMMON,
    "citizenship": "slovenské", "first_name": "Jana", "last_name": "Nováková",
    "birth_surname": "Nováková", "birth_date": "18.04.2008", "gender": "žena",
    "birth_place": "Trenčín", "birth_country": "Slovensko", "rodne_cislo": "080418/1234",
    "phone": "+421 900 111 101", "email": "jana.novakova@example.org",
    "perm_street": "Školská 12", "perm_city": "Trenčín", "perm_zip": "911 01",
    "perm_district": "Trenčín", "perm_country": "Slovensko", "has_corr_address": "nie",
    "university": "Slovenská technická univerzita v Bratislave",
    "faculty": "Fakulta informatiky a informačných technológií",
    "program_0": "Informatika", "form_0": "denná", "foreign_language": "anglický",
    "maturita_year": "2027", "school_type": "gymnázium",
    "school_name": "Gymnázium Jána Holého (fiktívny názov)", "school_street": "Školská 12",
    "school_city": "Trenčín", "school_zip": "911 01", "school_country": "Slovensko",
    "school_code": "790200000", "field_of_study": "gymnázium", "field_code": "7902J00",
    "grades": [["Slovenský jazyk a literatúra", "1", "1", "2"], ["Matematika", "1", "2", "1"],
               ["Anglický jazyk", "1", "1", "1"], ["Informatika", "1", "1", "1"]],
    "grade_averages": ["1,25", "1,30", "1,25"],
    "maturita_subjects": [["Slovenský jazyk"], ["Matematika"], ["Anglický jazyk", "B2"]],
    "had_prev_study": "nie", "consent": "súhlasím", "attachments": ["ročníkové vysvedčenia"],
}

VZOR2 = {  # graduate with previous university study and employment
    **COMMON,
    "citizenship": "slovenské", "first_name": "Martin", "last_name": "Kováč",
    "birth_surname": "Kováč", "birth_date": "07.11.1996", "gender": "muž",
    "birth_place": "Žilina", "birth_country": "Slovensko", "rodne_cislo": "961107/1234",
    "phone": "+421 900 111 102", "email": "martin.kovac@example.org",
    "perm_street": "Horská 8", "perm_city": "Žilina", "perm_zip": "010 01",
    "perm_district": "Žilina", "perm_country": "Slovensko", "has_corr_address": "áno",
    "corr_street": "Dunajská 24", "corr_city": "Bratislava", "corr_zip": "811 08",
    "corr_district": "Bratislava I", "corr_country": "Slovensko",
    "university": "Univerzita Komenského v Bratislave",
    "faculty": "Fakulta matematiky, fyziky a informatiky",
    "program_0": "Aplikovaná informatika", "form_0": "externá", "method_0": "kombinovaná",
    "maturita_year": "2016", "school_type": "stredná odborná škola",
    "school_name": "Stredná priemyselná škola technická (fiktívny názov)",
    "school_street": "Technická 5", "school_city": "Žilina", "school_zip": "010 01",
    "school_country": "Slovensko", "field_of_study": "Informačné a sieťové technológie",
    "field_code": "2561M00",
    "grades": [["Slovenský jazyk a literatúra", "2", "2", "2", "2"],
               ["Matematika", "2", "2", "1", "2"], ["Anglický jazyk", "2", "1", "1", "1"],
               ["Informatika", "1", "1", "1", "1"]],
    "grade_averages": ["1,75"],
    "maturita_subjects": [["Slovenský jazyk", "", "74", "68", "", "2"],
                          ["Anglický jazyk", "B2", "82", "78", "", "1"],
                          ["Matematika", "", "79", "74", "", "2"]],
    "maturita_date": "24.05.2016", "maturita_average": "1,67",
    "had_prev_study": "áno", "prev_university": "Univerzita Príkladu (fiktívny názov)",
    "prev_faculty": "Fakulta techniky", "prev_program": "Informatika", "prev_field": "Informatika",
    "prev_level": "1", "prev_start": "09/2016", "prev_end": "06/2019", "prev_title": "Bc.",
    "job_previous": "Technická podpora, Príklad s.r.o.",
    "job_current": "Softvérový tester, Demo s.r.o.", "consent": "nesúhlasím",
    "attachments": ["kópia maturitného vysvedčenia", "kópia VŠ diplomu"],
}

VZOR3 = {  # foreign applicant living in Slovakia
    **COMMON,
    "citizenship": "ukrajinské", "first_name": "Olena", "last_name": "Melnyk",
    "birth_surname": "Melnyk", "birth_date": "12.08.2005", "gender": "žena",
    "birth_place": "Ľviv", "birth_country": "Ukrajina",
    "phone": "+421 900 111 103", "email": "olena.melnyk@example.org",
    "perm_street": "Ulica Lesná 7", "perm_city": "Ľviv", "perm_zip": "79000",
    "perm_district": "Ľvivská oblasť", "perm_country": "Ukrajina", "has_corr_address": "nie",
    "stay_street": "Hlavná 20", "stay_city": "Košice", "stay_zip": "040 01",
    "stay_district": "Košice I", "stay_country": "Slovensko",
    "university": "Technická univerzita v Košiciach",
    "faculty": "Fakulta elektrotechniky a informatiky", "program_0": "Informatika",
    "form_0": "denná", "maturita_year": "2023", "school_type": "iná",
    "school_name": "Stredná škola Príklad Ľviv (fiktívny názov)", "school_street": "Lesná 7",
    "school_city": "Ľviv", "school_zip": "79000", "school_country": "Ukrajina",
    "field_of_study_foreign": "Všeobecné stredné vzdelanie",
    "grades": [["Známky podľa zahraničného dokladu; priložiť preklad"]],
    "maturita_date": "30.06.2023", "had_prev_study": "nie", "consent": "súhlasím",
    "attachments": ["kópia dokladu o vzdelaní", "úradný preklad dokladu"],
}

SAMPLES = {"vzor1": VZOR1, "vzor2": VZOR2, "vzor3": VZOR3}
