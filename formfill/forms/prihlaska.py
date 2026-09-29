"""Known form: "Prihláška na vysokoškolské štúdium – bakalárske / spojené štúdium"
(MŠVVaŠ SR, 04/2022).

The three samples (vzor1-3) define the scenarios the assistant must handle:
  1. current-year maturant  -> school code, no last-year grades, maturita only subject+level
  2. graduate with previous university study and employment -> full maturita results,
     correspondence address, previous-study section, jobs
  3. foreign applicant -> residence in Slovakia, rodné číslo optional, foreign school

Anchors reference label texts of the real ``formular.docx`` (see ``formfill.filler``).
"""

from __future__ import annotations

from datetime import date

from ..fields import (ACADEMIC_YEAR, BOXES, CONTROL, LIST, MARK, ROW, STRIKE, TABLE,
                      Anchor, Field)
from ..validators import loose

FORM_ID = "prihlaska_vs_bc"
TITLE = "Prihláška na vysokoškolské štúdium (bakalárske / spojené štúdium)"
DESCRIPTION = (
    "Oficiálne tlačivo MŠVVaŠ SR, ktorým sa uchádzač hlási na bakalárske alebo spojené "
    "vysokoškolské štúdium. Obsahuje osobné údaje, adresy, zvolenú vysokú školu a študijné "
    "programy, údaje o strednej škole a maturite, predchádzajúce VŠ štúdium, zamestnanie, "
    "súhlas so spracúvaním osobných údajov a zoznam príloh. Vypĺňa sa veľkým tlačeným písmom."
)
DETECT_PHRASES = ["Prihláška na vysokoškolské štúdium", "Rok maturitnej skúšky", "Študijný program"]

YES_NO = ["áno", "nie"]
FOREIGNER = {"field": "_foreigner", "equals": True}
NOT_FOREIGNER = {"field": "_foreigner", "equals": False}
CURRENT = {"field": "_current_maturant", "equals": True}
GRADUATE = {"field": "_current_maturant", "equals": False}
HAS_CORR = {"field": "has_corr_address", "equals": "áno"}
PREV = {"field": "had_prev_study", "equals": "áno"}


def _address(prefix: str, after: str, group: str, when: dict | None, who: str) -> list[Field]:
    return [
        Field(f"{prefix}_street", f"{who} – ulica a číslo", f"Ulica a číslo ({who.lower()})?", group,
              anchor=Anchor("Ulica a číslo", after), when=when),
        Field(f"{prefix}_city", f"{who} – mesto (obec)", "Mesto alebo obec?", group,
              anchor=Anchor("Mesto (obec)", after), when=when),
        Field(f"{prefix}_zip", f"{who} – PSČ", "PSČ?", group, anchor=Anchor("PSČ", after),
              validator="zip", when=when),
        Field(f"{prefix}_district", f"{who} – okres", "Okres?", group, anchor=Anchor("Okres", after),
              when=when, help="Okres, v zahraničí oblasť/región."),
        Field(f"{prefix}_country", f"{who} – štát", "Štát?", group, anchor=Anchor("Štát", after),
              when=when, default="SLOVENSKO"),
    ]


def _program(i: int) -> list[Field]:
    after = "Detašované pracovisko"
    optional = i > 0
    when = {"field": f"program_{i}", "filled": True} if optional else None
    n = i + 1
    return [
        Field(f"program_{i}", f"Študijný program č. {n}",
              "Na aký študijný program sa hlásite?" if not optional
              else f"Chcete uviesť aj {n}. študijný program? Ak áno, aký (inak napíšte „nie“)?",
              "Štúdium", required=not optional, anchor=Anchor("Študijný program", after, nth=i),
              help="Jeden program na riadok, presne podľa ponuky fakulty."),
        Field(f"form_{i}", f"Forma štúdia (program č. {n})", "Denná alebo externá forma štúdia?",
              "Štúdium", options=["denná", "externá"], anchor=Anchor("Forma štúdia", after, nth=i),
              when=when),
        Field(f"method_{i}", f"Metóda štúdia (program č. {n})",
              "Metóda štúdia – prezenčná, dištančná alebo kombinovaná?", "Štúdium",
              options=["prezenčná", "dištančná", "kombinovaná"], default="prezenčná",
              anchor=Anchor("Metóda štúdia", after, nth=i), when=when,
              help="Ak fakulta metódu neuvádza, je to prezenčná metóda."),
    ]


FIELDS: list[Field] = [
    # --- Štúdium -----------------------------------------------------------------------
    Field("study_level", "Typ štúdia", "Hlásite sa na bakalárske štúdium, alebo na spojené "
          "(prvý a druhý stupeň v jednom celku, napr. medicína, právo)?", "Štúdium", kind=STRIKE,
          options=["bakalárske", "spojené"], default="bakalárske",
          option_texts={"bakalárske": "bakalárske – prvý stupeň",
                        "spojené": "spojené – prvý a druhý stupeň v jednom celku"},
          help="Nehodiaci sa typ štúdia sa v tlačive prečiarkne."),
    Field("academic_year", "Akademický rok", "Na ktorý akademický rok sa hlásite (napr. 2027/2028)?",
          "Štúdium", kind=ACADEMIC_YEAR, validator="academic_year",
          anchor=Anchor("Akademický rok")),
    Field("university", "Vysoká škola", "Na ktorú vysokú školu sa hlásite?", "Štúdium",
          anchor=Anchor("Vysoká škola")),
    Field("faculty", "Fakulta", "Na ktorú fakultu?", "Štúdium", anchor=Anchor("Fakulta")),
    Field("detached_workplace", "Detašované pracovisko",
          "Študujete na detašovanom pracovisku? Ak áno, na ktorom (inak „nie“)?", "Štúdium",
          required=False, anchor=Anchor("Detašované pracovisko")),
    *_program(0), *_program(1), *_program(2),
    Field("foreign_language", "Cudzí jazyk na prijímaciu skúšku",
          "Z ktorého cudzieho jazyka budete robiť prijímaciu skúšku (ak ju fakulta vyžaduje)?",
          "Štúdium", required=False,
          anchor=Anchor("Prijímaciu skúšku budem robiť z cudzieho jazyka")),

    # --- Osobné údaje -------------------------------------------------------------------
    Field("first_name", "Meno", "Ako sa voláte – meno?", "Osobné údaje", anchor=Anchor("Meno")),
    Field("last_name", "Priezvisko", "Priezvisko?", "Osobné údaje", anchor=Anchor("Priezvisko")),
    Field("birth_surname", "Rodné priezvisko", "Aké je vaše rodné priezvisko (aj keď je rovnaké)?",
          "Osobné údaje", anchor=Anchor("Rodné priezvisko")),
    Field("title", "Akademický titul", "Máte akademický titul (napr. Bc.)? Ak nie, napíšte „nie“.",
          "Osobné údaje", required=False, anchor=Anchor("Akademický titul")),
    Field("birth_date", "Dátum narodenia", "Dátum narodenia?", "Osobné údaje", kind=BOXES,
          validator="birth_date", anchor=Anchor("Dátum narodenia")),
    Field("gender", "Pohlavie", "Pohlavie – muž alebo žena?", "Osobné údaje", kind=MARK,
          options=["muž", "žena"], anchor=Anchor(after="Pohlavie")),
    Field("birth_place", "Miesto narodenia", "Kde ste sa narodili (mesto/obec)?", "Osobné údaje",
          anchor=Anchor("Miesto narodenia")),
    Field("birth_country", "Štát narodenia", "V ktorom štáte?", "Osobné údaje",
          anchor=Anchor("Štát", "Miesto narodenia"), default="SLOVENSKO"),
    Field("citizenship", "Štátne občianstvo", "Aké máte štátne občianstvo (napr. slovenské)?",
          "Osobné údaje", anchor=Anchor("Štátne občianstvo")),
    Field("rodne_cislo", "Rodné číslo", "Vaše rodné číslo?", "Osobné údaje", kind=BOXES,
          validator="rodne_cislo", anchor=Anchor("Rodné číslo"), when=NOT_FOREIGNER),
    Field("rodne_cislo_foreigner", "Rodné číslo (ak bolo pridelené MV SR)",
          "Pridelilo vám Ministerstvo vnútra SR rodné číslo? Ak áno, napíšte ho, inak „nie“.",
          "Osobné údaje", kind=BOXES, validator="rodne_cislo", required=False,
          anchor=Anchor("Rodné číslo"), when=FOREIGNER),
    Field("phone", "Telefón", "Telefónne číslo (nepovinné)?", "Osobné údaje", required=False,
          validator="phone", anchor=Anchor("Tel. č.")),
    Field("email", "E-mail", "E-mailová adresa?", "Osobné údaje", validator="email",
          uppercase=False, anchor=Anchor("E-mailová adresa")),

    # --- Adresy -------------------------------------------------------------------------
    *_address("perm", "Adresa trvalého bydliska", "Adresy", None, "Trvalé bydlisko"),
    Field("has_corr_address", "Iná korešpondenčná adresa",
          "Je vaša korešpondenčná adresa iná ako trvalé bydlisko?", "Adresy", kind=CONTROL,
          options=YES_NO, default="nie"),
    *_address("corr", "Korešpondenčná adresa", "Adresy", HAS_CORR, "Korešpondenčná adresa"),
    *_address("stay", "Miesto pobytu u cudzinca", "Adresy", FOREIGNER, "Pobyt na Slovensku"),

    # --- Stredná škola ------------------------------------------------------------------
    Field("maturita_year", "Rok maturitnej skúšky",
          "V ktorom roku ste maturovali (alebo budete maturovať)?", "Stredná škola",
          validator="year", anchor=Anchor("Rok maturitnej skúšky"),
          help="Maturanti v tomto školskom roku uvedú rok, v ktorom budú maturovať."),
    Field("school_type", "Typ strednej školy",
          "Aký typ strednej školy ste absolvovali – gymnázium, stredná odborná škola, stredné "
          "odborné učilište, konzervatórium, združená stredná škola, alebo iná?", "Stredná škola",
          kind=MARK, options=["gymnázium", "stredná odborná škola", "stredné odborné učilište",
                              "konzervatórium", "združená stredná škola", "iná"],
          anchor=Anchor(after="Absolvovaná stredná škola")),
    Field("school_name", "Názov strednej školy", "Presný názov strednej školy (podľa vysvedčenia)?",
          "Stredná škola", anchor=Anchor("Názov", "Absolvovaná stredná škola")),
    Field("school_street", "Stredná škola – ulica a číslo", "Adresa školy – ulica a číslo?",
          "Stredná škola", anchor=Anchor("Ulica a číslo", "Absolvovaná stredná škola")),
    Field("school_city", "Stredná škola – mesto", "Mesto školy?", "Stredná škola",
          anchor=Anchor("Mesto (obec)", "Absolvovaná stredná škola")),
    Field("school_zip", "Stredná škola – PSČ", "PSČ školy?", "Stredná škola", validator="zip",
          anchor=Anchor("PSČ", "Absolvovaná stredná škola")),
    Field("school_country", "Stredná škola – štát", "Štát, v ktorom je škola?", "Stredná škola",
          anchor=Anchor("Štát", "Absolvovaná stredná škola"), default="SLOVENSKO"),
    Field("school_code", "Kód strednej školy",
          "Kód vašej strednej školy (9-miestny, dostanete ho v škole alebo na crinfo.iedu.sk)?",
          "Stredná škola", kind=BOXES, validator="school_code",
          anchor=Anchor("Kód strednej školy"), when=CURRENT,
          help="Vypĺňajú len tohtoroční maturanti; kratší kód sa doplní nulami na 9 miest."),
    Field("field_of_study", "Študijný odbor", "Študijný odbor podľa vysvedčenia (napr. gymnázium, "
          "informačné a sieťové technológie)?", "Stredná škola",
          anchor=Anchor("Študijný odbor", "Absolvovaná stredná škola"), when=NOT_FOREIGNER),
    Field("field_of_study_foreign", "Dosiahnuté vzdelanie (zahraničné)",
          "Aké vzdelanie ste získali (napr. všeobecné stredné vzdelanie)?", "Stredná škola",
          anchor=Anchor("Študijný odbor", "Absolvovaná stredná škola"), when=FOREIGNER),
    Field("field_code", "Kód študijného odboru",
          "Kód študijného odboru zo vysvedčenia (7 znakov, napr. 7902J00)?", "Stredná škola",
          kind=BOXES, validator="field_code", anchor=Anchor("Kód študijného odboru"),
          when=NOT_FOREIGNER),
    Field("education_level", "Stupeň dosiahnutého vzdelania", "Stupeň vzdelania (písmeno z kódu "
          "odboru)?", "Stredná škola", kind=BOXES, derived=True,
          anchor=Anchor("Stupeň dosiahnutého vzdelania", "Kód študijného odboru"),
          help="5. znak kódu študijného odboru."),
    Field("grades", "Prospech v ročníkoch",
          "Aký bol váš prospech z predmetov v jednotlivých ročníkoch? Napíšte napr. "
          "„Matematika: 1, 2, 1“ – každý predmet na nový riadok (tohtoroční maturanti posledný "
          "ročník vynechajú). Ak to fakulta nevyžaduje, napíšte „nie“.", "Stredná škola",
          kind=TABLE, validator="grades_table", required=False,
          anchor=Anchor(table="Ročník"), columns=["predmet", "I.", "II.", "III.", "IV.", "V.", "VI."]),
    Field("grade_averages", "Priemerný prospech po ročníkoch",
          "Aký bol priemerný prospech v jednotlivých ročníkoch (napr. 1,25 1,30 1,25)?",
          "Stredná škola", kind=ROW, validator="averages", required=False,
          anchor=Anchor("Priemerný prospech", colon=False), when={"field": "grades", "filled": True}),
    Field("maturita_subjects", "Maturitné predmety",
          "Z ktorých predmetov maturujete/ste maturovali? Pri každom uveďte úroveň (napr. B2) a "
          "ak už máte výsledky: % a percentil externej časti, % písomnej formy a známku z ústnej. "
          "Každý predmet na nový riadok.", "Stredná škola", kind=TABLE, validator="table",
          required=False, anchor=Anchor(table="Predmet maturitnej skúšky"), when=NOT_FOREIGNER,
          columns=["predmet", "úroveň", "externá %", "percentil", "písomná forma %", "ústna forma známka"]),
    Field("maturita_date", "Dátum maturitnej skúšky", "Kedy ste zmaturovali (dátum)?",
          "Stredná škola", validator="date", required=False,
          anchor=Anchor("Dátum maturitnej skúšky"), when=GRADUATE),
    Field("maturita_average", "Priemer maturitnej skúšky", "Aký bol priemer z maturity?",
          "Stredná škola", validator="decimal2", required=False,
          anchor=Anchor("Priemer maturitnej skúšky"), when=GRADUATE),

    # --- Predchádzajúce VŠ štúdium a zamestnanie ----------------------------------------
    Field("had_prev_study", "Predchádzajúce VŠ štúdium",
          "Študovali ste už niekedy na vysokej škole (aj neukončené štúdium)?",
          "Predchádzajúce štúdium", kind=CONTROL, options=YES_NO, default="nie"),
    *[Field(f"prev_{k}", f"Predch. VŠ – {lab}", q, "Predchádzajúce štúdium", required=req,
            validator=val, anchor=Anchor(label, "Prehľad o predchádzajúcom"), when=PREV)
      for k, lab, q, label, req, val in [
          ("university", "vysoká škola", "Na ktorej vysokej škole?", "Vysoká škola", True, None),
          ("faculty", "fakulta", "Fakulta?", "Fakulta", True, None),
          ("detached", "detašované pracovisko", "Detašované pracovisko (ak áno)?",
           "Detašované pracovisko", False, None),
          ("program", "študijný program", "Študijný program?", "Študijný program", True, None),
          ("field", "študijný odbor", "Študijný odbor?", "Študijný odbor", True, None),
          ("level", "stupeň vzdelania", "Ak ste štúdium ukončili, aký stupeň (1, 2, 1+2 alebo 3)?",
           "Stupeň dosiahnutého vzdelania", False, None),
          ("start", "začiatok štúdia", "Kedy ste začali (MM/RRRR)?", "Začiatok štúdia", True,
           "month_year"),
          ("end", "skončenie štúdia", "Kedy ste skončili (MM/RRRR), ak ste skončili?",
           "Skončenie štúdia", False, "month_year"),
          ("title", "získaný titul", "Získali ste titul (napr. Bc.)?", "Akademický titul", False, None),
      ]],
    Field("job_previous", "Predchádzajúce zamestnanie",
          "Predchádzajúce zamestnanie – profesia a zamestnávateľ (ak nemáte, „nie“)?",
          "Zamestnanie", required=False, anchor=Anchor("Predchádzajúce")),
    Field("job_current", "Súčasné zamestnanie",
          "Súčasné zamestnanie – profesia a zamestnávateľ (ak nemáte, „nie“)?", "Zamestnanie",
          required=False, anchor=Anchor("Súčasné")),

    # --- Vyhlásenie ---------------------------------------------------------------------
    Field("consent", "Súhlas so spracúvaním údajov z príloh",
          "Súhlasíte so spracúvaním osobných údajov uvedených v prílohách k prihláške?",
          "Vyhlásenie", kind=STRIKE, options=["súhlasím", "nesúhlasím"],
          option_texts={"súhlasím": "Súhlasím", "nesúhlasím": "Nesúhlasím"}),
    Field("attachments", "Ďalšie prílohy",
          "Životopis a doklad o zaplatení poplatku sú v zozname príloh predtlačené. Prikladáte aj "
          "ďalšie prílohy (napr. kópia maturitného vysvedčenia)? Ak nie, napíšte „nie“.",
          "Vyhlásenie", kind=LIST, required=False, anchor=Anchor("kópia dokladu o zaplatení",
                                                                 colon=False)),
    Field("signature_date", "Dátum podpisu", "Aký dátum mám uviesť pri podpise (napr. dnešný)?",
          "Vyhlásenie", validator="date", anchor=Anchor("Dátum", "Prílohy k prihláške")),
]


def _academic_start_year(values: dict) -> int:
    year = values.get("academic_year")
    if year:
        return int(str(year)[:4])
    today = date.today()
    return today.year + 1 if today.month >= 9 else today.year


def derive(values: dict) -> dict:
    """Values computed from other answers (conditions + auto-filled fields)."""
    out: dict = {}
    citizenship = values.get("citizenship")
    if citizenship:
        out["_foreigner"] = not loose(citizenship).startswith(("sloven", "sr"))
    if values.get("maturita_year"):
        out["_current_maturant"] = int(values["maturita_year"]) >= _academic_start_year(values)
    code = values.get("field_code")
    if code and len(code) >= 5:
        out["education_level"] = code[4]  # note 12: 5th character = stupeň vzdelania
    return out
