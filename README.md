# Raumbuchung mit Genehmigungs-Workflow (`room_reservation`)

Odoo 19 CE Modul zur Verwaltung von Räumen und Buchungsanträgen mit
mehrstufiger Freigabe, Kapazitäts- und Ausstattungsprüfung.

> Status: **in Entwicklung** — dieses README ist das Gerüst gemäß Aufgabenstellung
> und wird während der Umsetzung befüllt.

---

## 1. Funktionsbeschreibung

### Motivation

Odoo 19 **Community** enthält kein Raumbuchungssystem. Das Modul `room`
(„Meeting Rooms") ist Enterprise-exklusiv und hängt zudem an `web_gantt`,
das ebenfalls nur in Enterprise verfügbar ist. Ebenso `appointment`.
In CE bleibt lediglich `calendar` — Termine ohne jedes Raum- oder
Ressourcenkonzept. Dieses Modul schließt genau diese Lücke.

### Fachlicher Umfang

<!-- TODO: nach Implementierung final beschreiben -->

- **Raumverwaltung** — Räume mit Kapazität, Standort und Ausstattung
- **Buchungsanträge** — Reservierung eines Raums für einen Zeitraum
- **Genehmigungs-Workflow** — Anträge werden durch Manager freigegeben
- **Konfliktfreiheit** — Doppelbelegungen werden systemseitig verhindert
- **Automatik** — überfällige, noch nicht genehmigte Anträge verfallen

### Datenmodell

| Model | Zweck |
| --- | --- |
| `booking.room` | Buchbarer Raum |
| `booking.room.equipment` | Ausstattungsmerkmal (Beamer, Whiteboard, …) |
| `booking.reservation` | Buchungsantrag |
| `res.users` (`_inherit`) | Erweiterung um eigene Reservierungen |

> Der Namespace `booking.*` wird bewusst statt `room.*` verwendet, um
> Kollisionen mit dem Enterprise-Modul `room` auszuschließen.

**`booking.room.equipment`**

| Feld | Typ | Anmerkung |
| --- | --- | --- |
| `name` | Char | erforderlich, übersetzbar, systemweit eindeutig |
| `active` | Boolean | Archivierung statt Löschen |
| `room_ids` | Many2many | Gegenstück zu `booking.room.equipment_ids` |

**`booking.room`**

| Feld | Typ | Anmerkung |
| --- | --- | --- |
| `name` | Char | erforderlich |
| `location` | Char | Gebäude oder Etage |
| `capacity` | Integer | erforderlich, per SQL-Constraint größer null |
| `description` | Text | |
| `color` | Integer | Farbgebung im Kalender |
| `active` | Boolean | Archivierung |
| `equipment_ids` | Many2many | vorhandene Ausstattung |
| `reservation_ids` | One2many | Buchungen des Raums |
| `reservation_count` | Integer | berechnet, aggregiert per `_read_group` |

**`booking.reservation`**

| Feld | Typ | Anmerkung |
| --- | --- | --- |
| `name` | Char | Referenz aus `ir.sequence` |
| `room_id` | Many2one | erforderlich, `ondelete="restrict"`, indiziert |
| `user_id` | Many2one | Organisator, Vorgabe ist der aktuelle Benutzer |
| `start` / `stop` | Datetime | erforderlich, per SQL-Constraint `stop > start` |
| `duration` | Float | berechnet und gespeichert, in Stunden |
| `attendee_count` | Integer | per SQL-Constraint größer null |
| `purpose` | Char | erforderlich |
| `required_equipment_ids` | Many2many | gewünschte Ausstattung |
| `state` | Selection | mit Änderungsverfolgung |
| `approver_id` | Many2one | wer freigegeben hat, schreibgeschützt |
| `approval_date` | Datetime | schreibgeschützt |

Das Model erbt `mail.thread` und `mail.activity.mixin` und erhält dadurch
Chatter, Follower und Aktivitäten aus dem Odoo-Standard.

### Status-Workflow

```
        ┌──────────────────────────────┐
        ↓                              │
     draft ──→ to_approve ──→ confirmed ──→ done
        │           │              │
        └───────────┴──────────────┴──→ cancelled ──┐
                                              ↑     │
                                              └─────┘ zurück nach draft
```

Erlaubte Übergänge sind als Datenstruktur `_TRANSITIONS` hinterlegt und werden
zentral in `_transition_to()` geprüft. Ein unzulässiger Wechsel wirft einen
`UserError` mit den Klartextbezeichnungen beider Zustände.

| Von | Erlaubt nach |
| --- | --- |
| `draft` | `to_approve`, `cancelled` |
| `to_approve` | `confirmed`, `draft`, `cancelled` |
| `confirmed` | `done`, `cancelled` |
| `done` | — |
| `cancelled` | `draft` |

Ein Raum gilt als belegt in den Zuständen `to_approve`, `confirmed` und `done`.
Entwürfe und Stornierungen blockieren ihn nicht.

### Geschäftsregeln

<!-- TODO: Verweise auf die Tests ergänzen, sobald diese stehen -->

| # | Regel | Umsetzung |
| --- | --- | --- |
| 1 | Keine Doppelbelegung eines Raums für überschneidende Zeiträume | `_check_no_overlap` |
| 2 | Teilnehmerzahl darf die Raumkapazität nicht überschreiten | `_check_capacity`, zusätzlich `_onchange_attendee_count` als Hinweis im Formular |
| 3 | Der Raum muss die gewünschte Ausstattung bieten | `_check_required_equipment` |
| 4 | Ende muss nach dem Beginn liegen | SQL-Constraint `_stop_after_start` |
| 5 | Keine Buchung in der Vergangenheit | `_check_start_not_in_past`, ausgelöst nur beim Schreiben von `start` |
| 6 | Freigabe ausschließlich durch die Manager-Gruppe | `action_approve` |

Die Überschneidungsprüfung nutzt halboffene Intervalle
(`start < other.stop AND stop > other.start`), sodass eine Buchung genau dann
beginnen darf, wenn die vorherige endet. Die Bedingung wird als Domain an die
Datenbank übergeben und mit `limit=1` ausgewertet, statt Datensätze zu laden.

### Berechtigungen

<!-- TODO: Zugriffsmatrix (Model × Gruppe × CRUD) ergänzen, sobald die
     ir.model.access.csv steht -->

| Gruppe | Rechte |
| --- | --- |
| `group_booking_user` | eigene Reservierungen anlegen und bearbeiten |
| `group_booking_manager` | Räume verwalten, alle Reservierungen freigeben |

`group_booking_manager` impliziert `group_booking_user`, dieser wiederum
`base.group_user`. Rechte werden dadurch nur einmal auf der untersten Stufe
vergeben.

Für Reservierungen sind Lese- und Schreibzugriff bewusst getrennt geregelt:

| Regel | Operationen | Domain | Gruppe |
| --- | --- | --- | --- |
| `reservation_rule_read_all` | lesen | alle Datensätze | User |
| `reservation_rule_own_write` | schreiben, anlegen, löschen | `user_id = user.id` | User |
| `reservation_rule_manager_all` | alle | alle Datensätze | Manager |

Damit ist die Raumbelegung für alle einsehbar, während Änderungen beim
Organisator bleiben. Manager erben die einschränkende Regel, werden durch die
dritte Regel aber wieder aufgeweitet, da Record Rules innerhalb und zwischen
Gruppen mit ODER verknüpft werden.

### Views und Navigation

<!-- TODO: ergänzen -->

---

## 2. Herangehensweise

### Architekturentscheidungen

| Entscheidung | Begründung | Verworfene Alternative |
| --- | --- | --- |
| Zeitraum als `Datetime start`/`stop`, `duration` computed | Odoo-Konvention (`calendar.event`); UTC-Speicherung und Zeitzonen-Anzeige übernimmt das Framework | `Date` plus Float-Uhrzeit — erzeugt eigene Zeitzonenlogik |
| Overlap über halboffene Intervalle (`A.start < B.stop AND A.stop > B.start`) | Back-to-back-Buchungen (10–11 Uhr, 11–12 Uhr) müssen zulässig bleiben | Geschlossene Intervalle — praxisuntauglich |
| Overlap-Prüfung als `@api.constrains` | Idiomatisch und direkt testbar; verbleibende Race Condition siehe [Abgrenzung](#abgrenzung-non-goals) | PostgreSQL-`EXCLUDE` mit `tstzrange` — wasserdicht, erzwingt aber die Extension `btree_gist` |
| Status-Wechsel über deklarative Übergangs-Map plus zentrale Transition-Methode | Neue Zustände ändern eine Datenstruktur statt jeder Action-Methode; ein parametrisierter Test deckt alle Kombinationen ab | Prüfung in jeder `action_*`-Methode — Open/Closed-Verletzung |
| Kapazitätsprüfung als `@api.onchange` **und** `@api.constrains` | `onchange` ist reine UI und schützt nicht bei Import oder API-Zugriff; erst `constrains` sichert die Integrität | Nur `onchange` |
| Vergangenheits-Prüfung als `@api.constrains("start")` | Odoo führt eine Bedingung nur für die tatsächlich geschriebenen Felder aus, sodass ein Statuswechsel sie nicht auslöst und eine laufende Buchung stornierbar bleibt | Überschriebene `create`- und `write`-Methoden — gleiches Verhalten, doppelter Code |
| Lesezugriff für alle, Schreibzugriff nur auf eigene Reservierungen | Belegung muss einsehbar sein, sonst ist der Kalender wertlos; getrennte Record Rules für `perm_read` und `perm_write`/`perm_unlink` | Nur eigene sichtbar — Raumbelegung nicht nachvollziehbar |
| Organisator als `res.users`, `depends` nur auf `base` und `mail` | Modul läuft auf jeder CE-Instanz ohne HR und bleibt isoliert testbar | `hr.employee` — fachlich näher (Abteilung, Vorgesetzter als Genehmiger), kostet aber die `hr`-Abhängigkeit; `res.partner` — erlaubt externe Bucher, macht aber „meine Buchungen" in Record Rules unsauber |
| Ausstattung als eigenes Model mit m2m-Relation | Filterbar über Domains und ohne Code-Änderung erweiterbar | `Selection`-Feld — nicht durch Anwender pflegbar |
| Cron-Schwelle über `ir.config_parameter` | Konfigurierbar statt hardcodiert; Tests setzen den Parameter, statt die Systemzeit zu manipulieren | Konstante im Code |
| Referenz über `ir.sequence` | Odoo-Standard für fachliche Belegnummern | Computed `display_name` aus Raum und Datum — nicht stabil referenzierbar |

### Vorgehen

Umsetzung in aufeinander aufbauenden Schritten, jeder Schritt ein eigener Commit.

<!-- TODO: Commit-Referenzen je Schritt ergänzen -->

1. **Gerüst** — Verzeichnisstruktur, `__manifest__.py` mit `depends` auf `base` und `mail`
2. **Models** — `booking.room.equipment`, `booking.room`, `booking.reservation`,
   Erweiterung von `res.users` um eigene Reservierungen
3. **Geschäftslogik** — Constraints, Status-Übergänge, computed fields
4. **Security** — Gruppen, Zugriffsrechte, Record Rules
5. **Views** — list, form, search, calendar sowie Menüs und Aktionen
6. **Erweiterung des Standards** — `res.users` um eigene Reservierungen
   ergänzen und das bestehende Benutzerformular per XPath um einen
   Smart-Button erweitern
7. **Automatisierung** — Sequenz, Scheduled Action, Aktivität für Genehmiger
8. **Tests** — Geschäftsregeln, Status-Übergänge, Zugriffsbeschränkung
9. **Dokumentation** — README vervollständigen

### Abgrenzung (Non-Goals)

Bewusst nicht umgesetzt, um den Umfang der Probearbeit zu wahren:

- **Multi-Company** — kein `company_id`; erfordert zusätzliche Record Rules ohne
  fachlichen Mehrwert für die gestellte Aufgabe
- **Wiederkehrende Buchungen** — Rekurrenzlogik ist ein eigenständiges Thema
- **Absicherung gegen konkurrierende Transaktionen** — die Overlap-Prüfung per
  `@api.constrains` kann bei zwei exakt gleichzeitig schreibenden Transaktionen
  theoretisch umgangen werden. Wasserdicht wäre ein PostgreSQL-`EXCLUDE`-Constraint
  über `tstzrange`, was die Extension `btree_gist` als Installationsvoraussetzung
  nach sich zöge. Bewusst zurückgestellt und hier dokumentiert.
- **Externe Bucher** — Reservierungen setzen einen Odoo-Benutzer voraus

---

## 3. Installationsanleitung

### Voraussetzungen

- Odoo 19.0 Community Edition
- PostgreSQL 16
- Python ≥ 3.10 (`MIN_PY_VERSION` laut `odoo/release.py`)

Für den mitgelieferten Weg über Container genügen Docker und Docker Compose;
Odoo und PostgreSQL bringt das Setup selbst mit.

### Installation in eine bestehende Odoo-Instanz

Nur das Verzeichnis `room_reservation/` ist das eigentliche Modul.

```bash
git clone https://github.com/Mognus/odoo19-room-reservation.git
cp -r odoo19-room-reservation/room_reservation /pfad/zum/addons-verzeichnis/
```

Anschließend Odoo neu starten, unter *Apps* die Modulliste aktualisieren und
„Room Reservations" installieren. Alternativ per Kommandozeile:

```bash
odoo -d <datenbank> -i room_reservation --stop-after-init
```

### Installation über Docker Compose

```bash
git clone https://github.com/Mognus/odoo19-room-reservation.git
cd odoo19-room-reservation

make install   # Datenbank anlegen und Modul installieren
make up        # Stack starten
```

Odoo ist danach unter http://localhost:8069 erreichbar, Anmeldung mit
`admin` / `admin`.

Ein vollständiger Neuaufbau von null, der die Installierbarkeit auf einer
frischen Instanz nachweist:

```bash
make fresh     # löscht alle Volumes und installiert neu
```

### Tests ausführen

```bash
make test
```

Entspricht:

```bash
docker compose run --rm odoo odoo -d rooms -u room_reservation \
    --test-enable --test-tags /room_reservation --stop-after-init
```

### Entwicklungsumgebung

Ausgeführt wird ausschließlich im Container. Lokal wird nichts installiert.

Damit ein Language Server `from odoo import …` auflösen kann, werden einmalig
die Odoo-Quellen flach ausgecheckt:

```bash
make dev-init
```

Das legt `.odoo-src/` an, von der Versionierung ausgeschlossen und
ausschließlich als Nachschlagewerk gedacht. `pyrightconfig.json` verweist über
`extraPaths` darauf. Die Laufzeitabhängigkeiten von Odoo werden bewusst nicht
lokal installiert, da Odoo im Container läuft.

Für das Linting genügt ein systemweit installiertes `ruff`:

```bash
make lint
```

---

## 4. Zeitaufwand

<!-- TODO: Ist-Werte nach Abschluss eintragen -->

| Arbeitspaket | Geplant | Tatsächlich |
| --- | --- | --- |
| Projektgerüst und Manifest | 0,5 h | |
| Models und Geschäftslogik | 1,5 h | |
| Views, Menüs, Security | 1,5 h | |
| Scheduled Action und Aktivitäten | 1,0 h | |
| Tests | 1,5 h | |
| Dokumentation und Git-Historie | 1,0 h | |
| **Summe** | **7,0 h** | |

---

## 5. Definition of Done

<!-- TODO: abhaken, sobald erfüllt und verifiziert -->

**Funktion**

- [ ] Modul ist auf einer frischen Odoo 19 CE Instanz ohne Fehler installierbar
- [ ] Deinstallation und Neuinstallation funktionieren fehlerfrei
- [ ] Alle Geschäftsregeln sind implementiert und greifen
- [ ] Der Status-Workflow ist vollständig durchlaufbar

**Codequalität**

- [ ] PEP8-konform, geprüft mit Linter
- [ ] Odoo-Konventionen für Struktur, Benennung und Manifest eingehalten
- [ ] Fehlerfälle werfen `UserError` bzw. `ValidationError` mit klarer Meldung
- [ ] Benutzertexte sind übersetzbar

**Security**

- [ ] Zugriffsrechte für alle Models definiert
- [ ] Record Rules greifen, aus Benutzersicht verifiziert

**Tests**

- [ ] Automatisierte Tests für alle Geschäftsregeln
- [ ] Tests für erlaubte und unerlaubte Status-Übergänge
- [ ] Test für die Zugriffsbeschränkung
- [ ] Gesamte Testsuite läuft grün

**Dokumentation und Abgabe**

- [ ] README vollständig, alle Platzhalter aufgelöst
- [ ] Nachvollziehbare Git-Historie mit thematisch getrennten Commits
- [ ] Repository auf GitHub verfügbar

---

## 6. Bewertungsmatrix

Gewichtung gemäß Aufgabenstellung, zur Selbsteinschätzung.

<!-- TODO: Selbsteinschätzung nach Abschluss eintragen -->

| Kriterium | Gewicht | Nachweis | Selbsteinschätzung |
| --- | --- | --- | --- |
| Codequalität und Tests | 50 % | | |
| Odoo-Kenntnisse | 20 % | | |
| Dokumentation | 20 % | | |
| Git-Historie | 10 % | | |
