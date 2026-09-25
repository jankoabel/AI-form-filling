# AI vypĺňanie tlačív

**Autor:** _doplňte svoje meno_

Systém, ktorý prijme prázdne tlačivo vo formáte `.docx`, pomocou LLM pochopí, o aký dokument ide,
kladením otázok získa od používateľa potrebné údaje, overí ich a vráti **vyplnené tlačivo v PDF**.
Celá konverzácia sa ukladá do databázy, takže sa v nej dá pokračovať aj po reštarte aplikácie.

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2 (SQLite, voliteľne PostgreSQL)
- **LLM:** Gemma 4 31B cez OpenRouter (ľubovoľný OpenAI-kompatibilný endpoint, napr. lokálna Ollama)
  a vstavaný offline „mock“ asistent
- **Rozhrania:** CLI (`formfill`), webový chat (bonus), REST API so Swagger dokumentáciou
- **PDF:** úprava pôvodného `.docx` + konverzia cez LibreOffice (headless)

---

## Rýchle spustenie (Docker)

```bash
cp .env.example .env          # voliteľne doplňte OPENROUTER_API_KEY
docker compose up --build -d
```

- webový chat: <http://localhost:8000>
- API dokumentácia: <http://localhost:8000/docs>

Bez API kľúča beží aplikácia s offline asistentom (pýta sa otázku po otázke), takže sa dá vyskúšať
aj bez internetu. S kľúčom z <https://openrouter.ai/keys> sa zapne Gemma (`google/gemma-4-31b-it:free`).

### CLI

CLI je klient REST API a je nainštalované v kontajneri:

```bash
docker compose exec api formfill new /forms/formular.docx   # nahrá tlačivo a spustí konverzáciu
docker compose exec api formfill list                       # zoznam konverzácií
docker compose exec api formfill chat <id>                  # pokračovanie (aj po reštarte)
docker compose exec api formfill download <id> -o /data/prihlaska.pdf
docker compose exec api formfill demo vzor2 -o /data/vzor2.pdf   # vyplní vzorovými údajmi bez LLM
```

Konverzáciu ukončíte príkazom `/koniec`; stav ostane uložený. Po potvrdení údajov CLI PDF automaticky stiahne.

### Testy

```bash
docker compose run --rm api pytest            # v kontajneri (vrátane reálnej konverzie do PDF)
# alebo lokálne
pip install -e ".[dev]" && pytest --cov=formfill
```

62 testov, pokrytie ~90 %. Testy nepotrebujú sieť ani API kľúč (LLM je nahradené falošným modelom
alebo offline asistentom; HTTP klient je testovaný cez `httpx.MockTransport`).

---

## Ako to funguje

```
 .docx ──► detekcia tlačiva ──► schéma polí ──► konverzácia (LLM) ──► validácia ──► zhrnutie
                │                    ▲                                                 │ „áno“
                │ neznáme tlačivo    │                                                 ▼
                └── osnova štítkov ──┘ (LLM navrhne polia)          PDF ◄── LibreOffice ◄── vyplnenie .docx
                                   SQLite: sessions + messages + stav konverzácie (JSON)
```

1. **Detekcia tlačiva.** Pri nahraní sa text dokumentu porovná s registrom známych tlačív. Priložená
   *Prihláška na vysokoškolské štúdium* má ručne vyladenú schému (~60 polí, podmienky, validácie).
   Pre **akékoľvek iné tlačivo** sa z dokumentu vyextrahujú štítky polí („Label:“) a LLM z nich
   navrhne schému – názov, popis, otázky, povinnosť a typ validácie.
2. **Konverzácia.** Engine vyberie ďalšie chýbajúce polia (po sekciách, max. 3 naraz) a LLM dostane
   stav formulára, históriu a správu používateľa. Vráti JSON s vytiahnutými hodnotami (môže ich byť
   viac naraz – „Som Jana Nováková, narodená 18. 4. 2008“) a textom ďalšej otázky.
3. **Validácia v kóde, nie v LLM.** Každú hodnotu overí a normalizuje Python: dátumy, PSČ, e-mail,
   telefón, akademický rok, rodné číslo (formát, kontrolná číslica, zhoda s dátumom narodenia
   a pohlavím), kód strednej školy (doplnenie núl na 9 miest podľa vysvetlivky 10), kód odboru
   (doplnenie „00“ podľa vysvetlivky 12). Neplatná hodnota sa neuloží a asistent sa opýta znova.
4. **Podmienky.** Otázky sa prispôsobujú situácii – presne podľa troch vzorov:
   - *maturant v tomto roku* (vzor 1): kód strednej školy, maturita len predmet a úroveň;
   - *absolvent* (vzor 2): výsledky maturity, predchádzajúce VŠ štúdium, zamestnanie, iná korešpondenčná adresa;
   - *cudzinec* (vzor 3): miesto pobytu na Slovensku, rodné číslo len ak ho pridelilo MV SR.
   Stupeň vzdelania sa odvodí automaticky z 5. znaku kódu odboru.
5. **Zhrnutie a opravy.** Keď sú údaje kompletné, asistent ukáže zhrnutie. Opravy sa dajú zadať
   voľne („zmeň e-mail na …“); ak oprava zapne nové polia (napr. iná korešpondenčná adresa), asistent
   sa na ne dopýta. Po „áno“ sa vygeneruje PDF. Opravy sú možné aj po vygenerovaní.
6. **Vyplnenie dokumentu.** Hodnoty sa zapisujú priamo do pôvodného `.docx`, takže PDF je
   verné originálu (pozri nižšie), a potom LibreOffice vytvorí PDF.

### Vypĺňanie `.docx` – kotvy namiesto súradníc

Polia nie sú viazané na pozície v XML, ale na **viditeľné štítky** (`Anchor(label, after, nth)`):
„Ulica a číslo“ *po* „Korešpondenčná adresa“. Vďaka tomu kód funguje pre bežné Word tlačivá a je
odolný voči drobným zmenám šablóny. Filler rozpoznáva konvencie formulára:

| Typ poľa | V tlačive | Ako sa vyplní |
|---|---|---|
| `text` | `Meno:            Priezvisko:` v jednej bunke | hodnota za štítok, „zje“ rezervované medzery, aby susedný štítok ostal na mieste |
| `boxes` | úzke bunky (dátum, rodné číslo, kódy) | jeden znak na políčko; oddeľovače („/“, „mesiac“) preskočí |
| `mark` | Pohlavie, typ strednej školy | „X“ do políčka vedľa možnosti, resp. **dovnútra nakresleného štvorčeka** (DrawingML aj VML) |
| `strike` | „bakalárske … alebo spojené …“, „Súhlasím/Nesúhlasím“ | nehodiacu sa možnosť **prečiarkne**, ako žiadajú vysvetlivky |
| `table` / `row` | prospech, maturita, priemery | do prázdnych riadkov / buniek tabuľky |
| `list` | Prílohy 3.–15. | do prázdnych číslovaných riadkov |

Hodnoty sa píšu veľkým tlačeným písmom (okrem e-mailu) modrým písmom ako vo vzoroch. Vyplnenie
začína vždy z nedotknutej šablóny, takže je idempotentné.

### Odolnosť

- Keď LLM zlyhá (timeout, limit bezplatného modelu, nevalidný JSON), ťah prevezme deterministický
  asistent – konverzácia sa nezasekne. Klient opakuje požiadavky pri 429/5xx a vypne JSON režim,
  ak ho model nepodporuje.
- LLM nikdy priamo nezapisuje do dokumentu: jeho výstup prejde whitelistom kľúčov a validáciou.
- Súbežné správy v tej istej konverzácii serializuje zámok; SQLite beží vo WAL režime.
- Každá konverzia do PDF má vlastný profil LibreOffice (paralelné generovanie).

---

## REST API

| Metóda | Cesta | Popis |
|---|---|---|
| `POST` | `/api/sessions` | nahratie `.docx` (multipart `file`) → nová konverzácia + prvá otázka |
| `GET` | `/api/sessions` | zoznam konverzácií s postupom |
| `GET` | `/api/sessions/{id}` | detail: správy, zadané hodnoty, fáza |
| `POST` | `/api/sessions/{id}/messages` | `{"content": "..."}` → odpoveď asistenta |
| `GET` | `/api/sessions/{id}/pdf` | stiahnutie vyplneného PDF |
| `POST` | `/api/sessions/{id}/pdf` | opätovné vygenerovanie PDF |
| `DELETE` | `/api/sessions/{id}` | zmazanie konverzácie a súborov |
| `GET` | `/api/health` | stav a použitý LLM |

## Databáza

Tabuľky `form_sessions` (šablóna, snímka schémy polí, stav konverzácie ako JSON, fáza, cesta k PDF)
a `messages` (celá história vrátane zdroja odpovede – `llm` / `rule` / `rule-fallback`). Schéma sa
ukladá ku konverzácii, takže rozpracovaná konverzácia je konzistentná aj po zmene kódu.
Predvolene SQLite v Docker volume; PostgreSQL: `docker compose --profile postgres up` a v `.env`
`DATABASE_URL=postgresql+psycopg://formfill:formfill@db:5432/formfill`.

## Konfigurácia (`.env`)

| Premenná | Predvolená hodnota | |
|---|---|---|
| `OPENROUTER_API_KEY` | – | bez kľúča sa použije offline asistent |
| `LLM_PROVIDER` | `openrouter` ak je kľúč, inak `mock` | |
| `LLM_MODEL` | `google/gemma-4-31b-it:free` | |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | napr. `http://host.docker.internal:11434/v1` pre Ollamu |
| `DATABASE_URL` | `sqlite:////data/formfill.db` | |

## Štruktúra projektu

```
formfill/
  api.py            FastAPI aplikácia (REST + statický web)
  service.py        orchestrácia: nahratie → detekcia → konverzácia → PDF, perzistencia
  engine.py         konverzačný engine (fázy, výber otázok, validácia, zhrnutie)
  brains.py         LLMBrain (prompty, parsovanie) a RuleBrain (offline / fallback)
  fields.py         model poľa, kotvy, serializovateľné podmienky
  validators.py     validácie a normalizácia hodnôt
  forms/prihlaska.py  schéma priloženého tlačiva
  forms/registry.py   detekcia tlačiva, osnova neznámeho tlačiva
  document.py       nízkoúrovňové úpravy DOCX (behy textu, bunky, tvary)
  filler.py         zápis hodnôt podľa kotiev
  pdf.py            konverzia cez LibreOffice
  llm/client.py     OpenAI-kompatibilný klient + robustné parsovanie JSON
  cli.py            CLI klient (Typer)
  static/index.html webový chat
tests/              pytest (validácie, filler nad reálnym formular.docx, engine, LLM, API, CLI)
forms/formular.docx priložené tlačivo
```

## Obmedzenia a možné rozšírenia

- Pre neznáme tlačivá sa automaticky rozpoznávajú textové polia za štítkom; zaškrtávacie políčka
  a tabuľky majú plnú podporu zatiaľ len v ručne definovaných schémach.
- Pole „Evidenčné číslo“, pečiatky, podpisy a Protokol o prijímacom konaní sa zámerne nevypĺňajú
  (patria škole alebo úradu).
- Rozšírenie: import údajov z priložených dokumentov (napr. vysvedčenia), streamovanie odpovedí,
  autentifikácia používateľov.
