# 🎙️ Antigravity Smart Voice Engine
> **Instant Push-to-Talk, Multi-Hotkey Voice Recorder & File Drop for Antigravity IDE & VS Code**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)]()

A lightweight, pure-local, zero-latency background voice recorder designed for **Google Antigravity IDE** and **VS Code**. It allows developers to speak naturally (especially in dialects like Egyptian Arabic) and drops compressed, crystal-clear audio directly into the active chat window using **Push-to-Talk** or **Toggle** shortcuts.

---

## 🌟 Key Features

* 🚀 **Zero Latency & Pure Local:** No Telegram bots, no external cloud relays. Instant drop via Windows Shell Clipboard (`CF_HDROP`).
* 🧠 **Multimodal AI Ready:** Delivers raw voice notes directly to Gemini / Claude / GPT multimodal models.
* 🗜️ **High-Efficiency M4A/AAC Audio:** Reduces audio file sizes by **~86%** compared to uncompressed WAV without any quality loss, saving disk space and upload bandwidth.
* 💊 **Dynamic Floating Capsule (Waveform Pill Widget):** Modern, frameless OLED-black pill at the bottom of the screen featuring:
  - 🔴 Pulsing recording dot indicator.
  - ⏱️ Real-time recording timer (`00:05`).
  - 📊 7-bar live audio equalizer dancing directly to microphone input volume (RMS).
  - ⚡ Instant feedback state (`⚡ تم اللصق!`) before auto-fading.
  - 🛡️ Zero focus stealing (`WS_EX_NOACTIVATE`) so writing/typing is never interrupted.
* ⌨️ **Simultaneous Multi-Hotkeys:** Supports multiple hotkeys at once:
  - `Ctrl + CapsLock` (Ergonomic left-hand trigger, safe from CapsLock toggling)
  - `F9` (Ideal for Logitech MX Master 3S mouse buttons)
  - `F10`
* 🖱️ **Active-Window Intelligence:** Auto-pastes (`Ctrl+V`) into the focused window/project, seamlessly supporting multi-workspace setups.
* 🤫 **Silent Background Daemon:** Runs silently via `pythonw.exe` without popping up command prompt windows. Auto-starts on Windows boot just like `ScreenshotAutoSaver`.

---

## 🚀 Quick Start

### 1. Requirements & Installation
Ensure Python 3.10+ is installed on Windows.
```bash
git clone https://github.com/your-username/antigravity-voice-engine.git
cd antigravity-voice-engine
pip install -r requirements.txt
```

### 2. Run
* **Run in background (Silent):** Double-click `start_voice_silent.vbs`
* **Run with live logs:** Double-click `start_voice_console.bat`
* **Install to Windows Startup (Auto-run on boot):** Double-click `install_startup.bat`
* **Stop:** Double-click `stop_voice.bat`

---

## ⚙️ Configuration (`config.json`)

All features are fully dynamic and customizable:

```json
{
  "hotkey": "CTRL+CAPSLOCK, F9, F10",
  "mode": "smart",
  "audio_format": "m4a",
  "bitrate": "96k",
  "smart_hold_threshold_sec": 0.45,
  "min_recording_duration_sec": 0.6,
  "max_recording_duration_sec": 600,
  "sample_rate": 44100,
  "channels": 1,
  "save_directory": "C:\\Users\\USER\\Documents\\تسجيلات الصوت",
  "auto_paste": true,
  "paste_delay_ms": 150,
  "auto_send_enter": false
}
```

---

## 🧪 Testing
Run the test suite with pytest:
```bash
pytest tests/test_voice_engine.py -v
```

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).


---

<!-- آخر رقم مشكلة مستخدم: #7 -->

## 🔒 الدستور المعماري الصارم (Immutable Architectural Governance)

- 🚫 **ممنوع منعاً باتاً** إضافة أو ربط أي محرك تفريغ صوتي خارجي (سواء Gemini API خارجي، Whisper، سحابة، أو تطبيقات طرف ثالث لتحويل الصوت لنص).
- 🎯 **حدود المسؤولية الثابتة:** يعمل هذا المشروع حصرياً كأداة محلية صامتة لتسجيل الصوت وإلقاء ملف الصوت (`.m4a`) مباشرة عبر الحافظة (`CF_HDROP`) داخل **Antigravity IDE** فقط، حيث يتولى Antigravity داخلياً فهم الصوت مباشرة دون كسر المعمارية أو الحوكمة.
- 📂 **معيار تسمية الملفات الموحد:** `Voice_YYYY-MM-DD_HH-MM-SS.m4a` بدون كتابة اسم اليوم النصي لضمان الترتيب الزمني التلقائي السليم داخل المجلد.

---

## 📊 الحالة العامة والإصدار
- **الإصدار الحالي:** `v2.0.0` (SRE Focus-Safe & 4K High-DPI Edition)
- **الحالة العامة:** شغال ومستقر في الخلفية بنسبة 100% (`13/13` اختبار آلي ناجح) ✅

---

## 📁 الملفات الجديدة
- `.agents/rules/00-architecture-governance.md` — وثيقة الحوكمة المعمارية غير القابلة للتغيير لمنع أي تفريغ خارجي.

---

## 🐛 سجل المشاكل

| #رقم | [TAG] | وصف المشكلة | الأعراض | السبب | الحل | الحالة |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| #4 | [Script] | طباعة حرف `ر` بالعربي أو `v` بالإنجليزي بدلاً من لصق الفويس | عند إيقاف التسجيل بـ `Ctrl+CapsLock` أو `F9` أو `F10` يظهر حرف `ر` أو `v` في مربع الشات بدلاً من إرفاق ملف الصوت | استدعاء `ffmpeg.exe` عبر `subprocess.run` تحت `pythonw.exe` بدون `CREATE_NO_WINDOW` كان يفتح نافذة خفية تسرق الفوكس فتضيع ضغطة `Ctrl` وتصل `V` منفردة للشات، إضافة لعدم انتظار رفع أصابع المستخدم من أزرار الاختصار | إضافة `CREATE_NO_WINDOW` و `SW_HIDE` لـ `ffmpeg` + بناء `SendInput` 64-bit قياسي بفاصل استقرار `35ms` + انتظار تحرير كافة الأزرار الفيزيائية قبل اللصق | محلولة بالكامل ✅ |
| #5 | [Frontend] | تفعيل شريط القوائم العلوي عند استخدام زر `F10` وتبديل لمبة `CapsLock` | خروج مؤشر الكتابة من الشات نحو قائمة `File` عند ضغط `F10` | الاعتماد على `GetAsyncKeyState` فقط يرصد الزر دون منعه من الوصول لنظام ويندوز | بناء مستمع هجين بـ `WH_KEYBOARD_LL` يبلع ضغطات `F9` و `F10` و `CapsLock` (مع `Ctrl`) قبل وصولها للنظام مع إبقاء حارس `GetAsyncKeyState` للنوافذ الإدارية والماوس | محلولة بالكامل ✅ |
| #6 | [UI] | صعود كبسولة التسجيل لأعلى يسار الشاشة وصغر حجمها | ظهور الكبسولة صغيرة في الربع العلوي الأيسر بدلاً من أسفل المنتصف على شاشة 4K | غياب تفعيل `Per-Monitor DPI Awareness v2` واعتماد Tkinter على إحداثيات مخبأة وتطبيق `WS_EX_NOACTIVATE` على `TkChild` بدلاً من `TkTopLevel` | تفعيل `SetProcessDpiAwarenessContext(-4)` مبكراً واستعلام حي لـ `GetMonitorInfoW` و `GetDpiForMonitor` وتطبيق أنماط Win32 على `GetAncestor(..., GA_ROOT)` | محلولة بالكامل ✅ |
| #7 | [Config] | عدم انتظام ترتيب ملفات الصوت زمنياً وتكرار مشغل الاختصارات في Startup | تشتت ترتيب التسجيلات في المجلد وظهور نسختين من `ArabicShortcutsFix` | وجود اسم اليوم (`%A`) في بداية اسم الملف، ووجود ملفي `.cmd` و `.vbs` معاً في مجلد Startup | إزالة اسم اليوم ليصبح التنسيق `Voice_YYYY-MM-DD_HH-MM-SS.m4a` وحذف النسخة المكررة `.cmd` مع حفظ نسخة احتياطية | محلولة بالكامل ✅ |

---

## 💡 دروس مستفادة

| #رقم | [TAG] | الدرس | السياق |
| :--- | :--- | :--- | :--- |
| #4 | [Script] | أي عملية `subprocess` تُستدعى من تطبيق يعمل بـ `pythonw.exe` يجب تزويدها بـ `CREATE_NO_WINDOW` وإلا سرقت الفوكس من نافذة المستخدم لحظة الإغلاق | إصلاح ضياع اختصار `Ctrl+V` وطباعة حرف `ر`/`v` أثناء ضغط الصوت بـ `ffmpeg` |
| #5 | [Script] | في Win64 `ctypes` يجب أن يشمل اتحاد `INPUT` بنية `MOUSEINPUT` كاملة ليبلغ الحجم 40 بايت بالضبط، ويجب انتظار تحرير الأزرار الفيزيائية قبل حقن `Ctrl+V` | محاكاة اللصق الذري المستقر مع وجود AutoHotkey وتعدد اللغات |
| #6 | [UI] | في نوافذ Tkinter ذات `overrideredirect(True)` يُرجع `winfo_id()` النافذة الابنة `TkChild`؛ ولتجنب سرقة الفوكس وضبط الـ 4K يجب تعديل `GetAncestor(hwnd, GA_ROOT)` واستعلام `GetMonitorInfoW` حياً | تثبيت كبسولة الصوت العائمة على شاشة 4K بتكبير 225% |
| #7 | [Config] | تسمية الملفات الأرشيفية يجب أن تتبع المعيار الرقمي التنازلي `YYYY-MM-DD_HH-MM-SS` بدون أسماء أيام الأسبوع لضمان تطابق الترتيب الأبجدي مع الترتيب الزمني | أرشفة تسجيلات الصوت في مستكشف ويندوز |

---

## 🚀 سجل الإنجازات
- تثبيت دستور الحوكمة المعمارية الصارم (صفر تفريغ خارجي؛ إلقاء ملف صوتي خام لـ Antigravity IDE فقط).
- القضاء الجذري 100% على مشكلة ظهور حرف `ر` / `v` وسرقة فوكس `ffmpeg` وتعارض الأزرار.
- بناء نظام الاستماع الهجين `WH_KEYBOARD_LL` لبلع `F10` و `F9` و `CapsLock` ومنع فتح قوائم الويندوز.
- ترقية الكبسولة العائمة لدعم شاشات 4K وتكبير `225%` ديناميكياً فوق شريط المهام مع خاصية الاختراق للماوس (`Click-Through`).
- تعديل صيغة أسماء التسجيلات إلى `Voice_YYYY-MM-DD_HH-MM-SS.m4a` وتنظيف التكرار من مجلد بدء التشغيل واجتياز 13 اختباراً آلياً.


---

<!-- آخر رقم مشكلة مستخدم: #11 -->

## 🛡️ ترقية الاعتمادية الشاملة v2.1 (SRE Gate-1 Hardening)

### 📌 السلوكيات التشغيلية الموثقة:
- **إيقاف الخدمة في الخلفية (`stop_voice.bat`):** يرسل إشارة إيقاف رشيق عبر حدث ويندوز المسمى `Local\AntigravityVoiceEngine_Shutdown` لإغلاق المايك والهوك والكبسولة بأمان دون قتل قسري.
- **الإعدادات المحلية الخاصة (`config.local.json`):** يمكنك إنشاء ملف `config.local.json` (متجاهل في Git) لتخصيص أي مفتاح فرعي مع دمج عميق تلقائي (`_deep_merge`) فوق `config.json`.
- **سلوك الحافظة (`Clipboard`):** يحتفظ المحرك عمداً بآخر ملف صوتي مسجل داخل الحافظة (`CF_HDROP`) بعد اللصق التلقائي، مما يتيح لك إعادة لصقه يدوياً بـ `Ctrl+V` في أي نافذة أخرى متى شئت.
- **حماية المجلدات وشاشات الصلاحيات (`Explorer` / `UAC` / `Win+L`):** يمنع المحرك تلقائياً إرسال `Ctrl+V` داخل مستكشف الملفات `explorer.exe` (لمنع نسخ ملفات الصوت بالخطأ وسط مجلداتك)، وعند ظهور شاشة صلاحيات المسؤول (`UAC`) أو قفل الشاشة (`Win+L`) يُحفظ التسجيل بأمان على القرص وفي الحافظة دون محاولة لصق عمياء.
- **مسبار التعافي الذاتي للهوك (`Self-Healing WH_KEYBOARD_LL`):** يفحص المحرك استجابة الهوك كل ثانيتين أثناء الخمول ويعيد تركيبه تلقائياً إذا أزاله النظام بصمت.

### 📁 الملفات المضافة في v2.1
- `win32_api.py` — مصدر موحد لكافة هياكل وتواقيع دوال Win32 بمعمارية 64-bit مع `use_last_error=True`.
- `stop_voice.bat` — أداة الإيقاف الرشيق للخدمة الخلفية عبر `EventWaitHandle`.
- `tests/test_p0_characterization.py` — حزمة اختبارات التوصيف والحالات الحدية المعزولة.
- `.github/workflows/ci.yml` و `requirements-dev.txt` — مصفوفة التكامل المستمر الآلي على بايثون `3.10–3.13`.

### 🐛 إضافات سجل المشاكل (v2.1)

| #رقم | [TAG] | وصف المشكلة | الأعراض | السبب | الحل | الحالة |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| #8 | [Script] | تحول وضع الضغط المطول `hold` إلى `toggle` خلال `35ms` (`HK-11`) | عند تفعيل كبت المفتاح في `WH_KEYBOARD_LL` يقرأ `GetAsyncKeyState` القيمة `0` فيطلق الـ Watchdog حدث `release` مبكر | نواة `win32k` لا تحدّث جدول `gafAsyncKeyState` للمفاتيح المبلوعة بـ `return 1` | فصل ملكية القواعد المفعلة عبر الهوك (`activated_by_hook`) + مجموعة التتبع الفيزيائي `_phys_down` والكبت المتماثل `_suppressed_down` | محلولة بالكامل ✅ |
| #9 | [Security] | عودة صامتة لفتح قوائم `F10` إذا أسقط الويندوز الهوك (`HK-01`/`HK-07`) | فقدان كبت الأزرار بصمت عند تجاوز `LowLevelHooksTimeout` | غياب آلية فحص حياة `WH_KEYBOARD_LL` بعد التركيب | إضافة مسبار نبض سحري `VK_NONAME + 0x41475956` كل ثانيتين أثناء الخمول يعيد تركيب الهوك تلقائياً عند انقطاعه | محلولة بالكامل ✅ |
| #10 | [UI] | إظهار شارة `تم اللصق` رغم فشل الحقن في نوافذ المسؤول (`EN-01`/`CB-11`) | ظهور رسالة نجاح كاذبة عند حظر `SendInput` بواسطة UIPI | عدم فحص القيمة الراجعة لـ `simulate_paste` ووجود مسار `keybd_event` بلا قيمة خطأ | حذف مسار `keybd_event` الكاذب وفحص عائد `SendInput` وإظهار شارة صادقة `حُفظ (الصق بـ Ctrl+V)` عند التعذر | محلولة بالكامل ✅ |
| #11 | [Config] | احتمالية نسخ ملف الصوت داخل مجلد مفتوح في `Explorer` (`CB-01`) | ضغط `Ctrl+V` تلقائياً عندما تكون نافذة `explorer.exe` في المقدمة ينسخ ملف الصوت للمجلد | عدم التحقق من اسم العملية الهدف قبل اللصق | فحص اسم العملية عبر `QueryFullProcessImageNameW` وحظر اللصق التلقائي في `explorer.exe` مع إبقاء الملف جاهزاً في الحافظة | محلولة بالكامل ✅ |
