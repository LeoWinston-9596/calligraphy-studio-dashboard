# Calligraphy & Art Studio — Local Dashboard

[![tests](https://github.com/LeoWinston-9596/calligraphy-studio-dashboard/actions/workflows/tests.yml/badge.svg)](https://github.com/LeoWinston-9596/calligraphy-studio-dashboard/actions/workflows/tests.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[简体中文](README.md) · **English**

> **Why** — Teachers at a calligraphy studio track student work and lesson balances from
> their phones. The spreadsheets exported by the school-management app are unreadable, and
> because teachers hold classes without deducting lessons, the "remaining lessons" figure
> drifts high — which quietly breaks every renewal reminder built on it.
>
> **Hardest part** — Mobile browsers **withhold microphone access from HTTPS pages whose
> certificate isn't system-trusted**. Tapping "continue anyway" doesn't help:
> `navigator.mediaDevices` simply doesn't exist. So the app self-signs a certificate and
> walks the user through installing it as a trusted root — via a `.mobileconfig` profile on
> iOS (Safari only; WeChat and Chrome silently cannot), and an entirely different path on
> Android. Apple additionally rejects certificates valid for more than 825 days or missing
> the `serverAuth` extension, so a naive 10-year cert installs but still fails.
>
> **What I'd change** — Accounts were designed for a single location; multi-branch would
> need a rework. The follow-up teacher started as a single-value field before I learned a
> student can have different teachers in different classes — that cost a table migration
> which asking one more question up front would have avoided.

Turns spreadsheets exported from a school-management app into a searchable dashboard,
and lets teachers upload student artwork with voice or text feedback from their phones.

**Runs entirely on your LAN with zero internet dependency** — unplug the WAN cable and
everything keeps working.

---

## 1. Running it

| OS | How |
|------|------|
| macOS | double-click **`启动.command`** |
| Windows | double-click **`启动.bat`** |
| Any (CLI) | `python run.py` |

First launch does three things automatically: create a `.venv`, install dependencies,
build the frontend. Later launches take seconds.

> Requires **Python 3.11+**.
> A prebuilt `web/dist` is committed, so **Node.js is not required** to run —
> you only need it if you want to modify the frontend source.

The console prints the addresses to use:

```
Desktop    http://192.168.x.x:8000
Phone      https://192.168.x.x:8443   ← required for voice recording
Login      admin / admin123 (forced password change on first login)
```

Stop with `Ctrl + C`.

### Two things are required for phone recording

**① Open the `https://…:8443` address.** Browsers block microphone access over plain HTTP.
If you opened the HTTP address, a blue banner appears at the top — one tap jumps to the
same page over HTTPS.

**② Install the certificate as a trusted root on the phone.**

This step is easy to miss: **tapping "continue anyway" is not enough.** iOS Safari and
Android Chrome will not hand `navigator.mediaDevices` to the page unless the certificate
is trusted by the system. The address bar says https, but the recording button still
won't appear.

Open **`https://…:8443/cert/help`** on the phone and follow the steps (iOS and Android
both covered). There is also an entry point under Settings → Voice Recording Setup.

**On iPhone you must use Safari.** WeChat's in-app browser and Chrome cannot install
configuration profiles — the page detects this and tells you to switch. iPhone gets a
`.mobileconfig` profile; Safari will prompt "This website is trying to download a
configuration profile" — allow it.

> Two iPhone gotchas — miss either one and it won't work:
> 1. The download **does not auto-install**. Go to `Settings`, tap "Profile Downloaded"
>    at the top (or `Settings → General → VPN & Device Management`).
> 2. After installing you must go to
>    `Settings → General → About → Certificate Trust Settings` and **turn the switch on**.

Skipping this is fine — the recorder degrades to a file upload (teachers record with
Voice Memos and pick the file). Photos and text feedback are unaffected.

Settings has a "Voice Recording Setup" panel showing the phone's secure-context status
and whether the microphone and recording APIs are available — screenshot it when
troubleshooting.

---

## 2. Daily workflow

1. **Import data** (More → Data Import): drag in the exported spreadsheets, review the
   first 5 rows, confirm. File type is detected from column names.
2. **Teachers upload work** (Workbench): My Classes → class → student → photo →
   voice/text → submit.
3. **Review**: search students, check lesson balances and the artwork timeline; watch the
   alerts board for renewals, expiries and absences.

### Four supported spreadsheets

| File | Goes to | Notes |
|------|------|------|
| Enrolled student roster `.xls` | Student records | Keyed on student number; falls back to name + phone |
| Course enrollments `.xls` | Lesson accounts (core) | Reads only the `报读课程` sheet; also builds the class → course map |
| Order export `.xlsx` | Orders (read-only) | |
| Transaction detail `.xls` | Transactions (read-only) | |

Imports are **full-table replacements**: the new file wins, so **re-importing the same
file never duplicates data**. Imports do **not** count as edits and never raise an edit badge.

---

## 3. Two ways of counting remaining lessons

The "remaining" figure from the management app is only accurate at the moment of export.
Once teachers hold classes without deducting lessons, it drifts high. So there are two
modes, switchable in Settings (estimated is the default):

- **As-imported**: shows the raw `remaining` value from the spreadsheet.
- **Estimated**: `imported remaining − lessons evaluated since the import`.
  Multiple evaluations for the same student, course and **same day count as one lesson**;
  delete all of that day's evaluations and the balance rolls back.

The UI shows `about N lessons`; tap it to see the arithmetic:

```
7 at import (Aug 1) − 2 evaluations = about 5
```

The alerts board thresholds follow whichever mode is active.

**Variance report**: after each course-enrollment import, the system compares
"last period's estimate vs this period's imported figure" and lists every student whose
delta is non-zero (viewable any time from the import page). It only reports —
**it never modifies data**.

---

## 4. Edit trail

Student info, artwork and feedback, follow-up status, comment templates — **every edit is
recorded**.

An orange badge appears at the top-right of the card:

| Edits | Badge |
|---------|------|
| 0 | none |
| 1 | Edited |
| 2 | Edited twice |
| ≥3 | Edited multiple times |

Tap the badge for the full history: who, when, which field, before → after.
Deleting artwork is a **soft delete** — hidden from the timeline, still in the edit log,
and the estimated balance rolls back accordingly.

---

## 5. Speech-to-text (optional)

Voice feedback can be transcribed automatically. **This is optional — skipping it does
not affect anything else**, you just don't get transcripts.

### One-time install

```bash
python install_asr.py      # ~228MB, the only step that needs internet
```

Restart afterwards. New recordings transcribe automatically; for existing ones use
"Re-transcribe all" under Settings → Speech-to-Text.

The engine is **SenseVoice-Small** (ONNX via sherpa-onnx, CPU-only, **no PyTorch**).
Transcription is fully offline and measured at **40× realtime on CPU** — a 60-second
recording takes about 1.5 seconds. It runs in a background queue, so **submitting is
instant** for the teacher.

### Why there's a glossary

Speech recognition reliably mangles domain terms into homophones. Measured on real audio:

| Intended | Recognised as |
|---|---|
| 提按 (press-and-lift) | 提案 (proposal) |
| 皴法 (texture stroke) | 村法 |
| 藏锋 (hidden tip) | 藏风 |

So transcripts get a pinyin-based correction pass against a glossary. 56 common
calligraphy and painting terms are built in; staff can add or remove entries under
Settings → Speech-to-Text, and **paste a sentence to preview** what would be corrected.

After extending the glossary, hit "Re-transcribe all" to re-run earlier recordings.
**Anything a teacher has manually proofread is never overwritten.**

### Teachers can fix it

Each voice entry in the timeline shows its transcript with a "Proofread" button.
Edited transcripts are marked **Manually proofread** and go through the normal
**edit trail** (who changed what, before → after).

Exported portfolios include the transcript — previously the printed version only had an
audio link, which meant the voice feedback was effectively lost on paper.

---

## 6. China network notes

**Daily use needs no internet at all.** Only three *installation* steps go online, and all
of them fall back to domestic mirrors automatically:

| Step | Default | Automatic fallback |
|---|---|---|
| Python dependencies | PyPI | Tsinghua TUNA → Aliyun |
| Speech model | hf-mirror.com | ModelScope → HuggingFace → GitHub |
| Frontend build (rarely needed) | npmjs | npmmirror |

Failures switch sources automatically. To force one:

```bash
SBS_PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple python run.py
python install_asr.py --source modelscope
python install_asr.py --list          # show all sources
```

The model download pulls the 228MB int8 file directly rather than the 999MB GitHub
tarball (937MB of which is an fp32 model this project never uses).

**Fully air-gapped machine?** Download `model.int8.onnx` and `tokens.txt` elsewhere, drop
them in `data/models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/`, restart.
Or `python install_asr.py --file <tarball>`.

---

## 7. Backups

- Every day at **02:00** the database and media folder are incrementally archived to
  `backups/YYYY-MM-DD/`, keeping the last **30**.
- Settings shows the last backup time and has a manual backup button.
- If more than 48 hours pass without a backup, a yellow banner appears site-wide.

> Moving to another machine: copy the whole project folder — all data lives under `data/`.

---

## 8. Accounts, roles and class ownership

### Role hierarchy (accounts only, not data)

| | Create accounts | Deactivate | Can create |
|---|---|---|---|
| **Principal** | ✅ | Admin staff, teachers | Principal / Admin / Teacher |
| **Admin staff** | ✅ | Teachers | Admin / Teacher |
| **Teacher** | ❌ | ❌ | — |

The rule is "same level and below to create, strictly below to deactivate". Nobody can
deactivate themselves.

> **Business data is not restricted by role.** Students, lessons, artwork, feedback,
> imports, orders and transactions remain visible and editable to every signed-in user —
> traceability comes from the **edit trail**, not from permission walls. The hierarchy
> applies only to user management.

### Follow-up teachers: per class, multi-select

A student enrols in several classes, each possibly taught by a different teacher. So the
follow-up teacher is recorded per **(student, class)** pair, not per student. The student
detail page has a "Classes & Follow-up" card with one row per class and a multi-select.
The "follow-up" field in the basic info card is a read-only aggregate.

> The management app exports only one follow-up person per student (and its
> "student manager" column is empty), so multi-teacher relationships can only be
> maintained here.

**Re-importing never wipes teachers you added by hand.** The imported value occupies a
dedicated slot; a new import replaces only that slot:

| Action | Result |
|---|---|
| Import (follow-up = Teacher Li) | `Teacher Li` |
| Manually add Teacher Wang | `Teacher Li, Teacher Wang` |
| Re-import the same file | `Teacher Li, Teacher Wang` (unchanged) |
| Management app changed to Teacher Zhao, then import | `Teacher Zhao, Teacher Wang` |

Changing follow-up teachers counts as an edit — the student card gets a badge, and the
log shows who changed which class from what to what.

### Class ownership follows the follow-up field

The system derives each teacher's classes from the follow-up data. **Adding a follow-up
teacher to a class immediately assigns that class to them** — including manual additions.

When creating a teacher account, typing the name **auto-selects** the matching identity
from the imported data and pulls in all their classes. One account can hold **multiple
identities** (union of their classes). The picker shows "Teacher Zhang (12 classes ·
30 students)" for confirmation.

Two class-assignment modes:

- **Follow the import** (default): new classes opened in the management app are assigned
  automatically after the next import — no need to come back and tick boxes.
- **Manual**: a fixed set of classes; new ones don't appear automatically.

Names are fuzzy-matched (an account called "Zhang San" matches "Teacher Zhang" in the
sheet); the match is displayed so you can override it.

---

## 9. Layout

```
.
├── 启动.command / 启动.bat   one-click launch (macOS / Windows)
├── run.py                    launcher: deps, certificates, dual-port serving
├── requirements.txt
├── app/                      backend (FastAPI + SQLite)
│   ├── main.py               app entry, router mounting, migrations
│   ├── models.py             data model
│   ├── importer.py           four spreadsheet parsers, replace-import, variance report
│   ├── balance.py            the two lesson-count modes
│   ├── editlog.py            edit trail
│   ├── exporter.py           portfolio HTML export
│   ├── backup.py             daily backup
│   ├── certs.py              self-signed certificate
│   ├── asr.py                speech-to-text (swappable engine)
│   ├── terms.py              homophone correction for domain terms
│   ├── transcribe_worker.py  background transcription queue
│   └── routers/              HTTP endpoints
├── web/                      frontend (Vue 3 + Vite)
│   └── dist/                 prebuilt, committed so Node isn't required
├── install_asr.py            speech model installer (optional)
├── tests/                    self-test suites
├── build.py / sbs.spec       packaging config
├── installer.iss             Windows installer config
├── data/                     runtime data (git-ignored)
└── backups/                  automatic backups (git-ignored)
```

---

## 10. Tests

```bash
# macOS
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python tests/acceptance.py            # the 7 acceptance criteria
.venv/bin/python tests/test_roles_teachers.py   # roles + teacher/class matching
.venv/bin/python tests/test_asr.py              # speech-to-text + glossary
.venv/bin/python tests/test_packaging.py        # frozen-app path resolution

# Windows
.venv\Scripts\python tests\acceptance.py
```

All suites use a throwaway data directory and **never touch your real data**.
Current result: **73 + 39 + 20 + 18 checks, all passing**.

> **Test data is not in this repository.** The real exports contain student names,
> guardian phone numbers and home addresses. Drop your own exports into the project root
> (any filename — detection is by column signature) and the suites pick them up.
> Without them, data-dependent checks skip cleanly instead of failing.

---

## 11. Deliberately out of scope

Scheduling, attendance, writing lesson deductions back to the source app, online payment,
push notifications, a parent-facing app, multi-campus, charts and reports.
