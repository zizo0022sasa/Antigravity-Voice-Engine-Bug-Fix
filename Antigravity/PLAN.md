# 🗺️ الخطة الهندسية الشاملة للإصدار v2.1 — النسخة المعدّلة لبوابة Gate-1 (`v2.1-rev2`)

- **حالة التنفيذ:** 🔒 **مُجمَّد برمجياً (`PLAN-ONLY / ZERO CODE TOUCHED`)** — أُدمجت التعديلات الإلزامية (`A1–A5`) والموصى بها (`R1–R10`) بالكامل انتظاراً لـ `APPROVED FOR EXECUTION`.
- **الدستور الحاكم:** [`.agents/rules/00-architecture-governance.md`](../.agents/rules/00-architecture-governance.md) (صفر STT خارجي، صفر اتصال بالشبكة).

---

## 🏛️ المبادئ التصميمية الحاكمة

1. **اختبارات التوصيف أولاً قبل أي إعادة هيكلة (`Characterization-First` — `A4`):** لا يُلمس أي ملف إنتاجي قبل كتابة اختبارات الوحدة المعزولة التي تحرس سلوك الهوك واللصق وحسابات الـ 4K.
2. **التماسك فوق عدّاد البايتات (`KISS` — `A4`):** أُلغي قيد `9.5KB` المصطنع؛ `win32_api.py` يُنشأ حصراً لمنع تكرار تعريفات `ctypes` وتوحيد `WinDLL(..., use_last_error=True)`.
3. **الفصل الواضح بين إعدادات المستخدم والثوابت الهندسية (`R6`):** إعدادات السلوك في `config.json` (+ دمج عميق لـ `config.local.json` — `R4`)، بينما التوقيتات الميكانيكية الداخلية (`35ms`, `50ms`, `950ms`, `2.0s`) ثوابت مسماة في الكود.

---

## 🛠️ مراحل التنفيذ بالترتيب الإلزامي (تُنفَّذ فقط بعد `APPROVED FOR EXECUTION`)

### 🔴 المرحلة P0 — اختبارات التوصيف، نموذج ملكية الهوك، والمسبار الذاتي، وصدق اللصق

- **[T-P0-00] اختبارات التوصيف المعزولة قبل الهيكلة (`A4`, `TS-02..06`):**
  - إنشاء اختبارات وحدة خالصة بـ Mocks (بدون لمس حافظة المطور أو المايك الحقيقي):
    1. اختبار `_low_level_proc` بـ `KBDLLHOOKSTRUCT` مصطنع: كبت `F10`/`F9`/`CapsLock`، الكبت المتماثل لـ `KeyUp`، حصرية المعدِّلات، وتجاهل `LLKHF_INJECTED` (ما عدا مسبار النبض السحري).
    2. اختبار `HK-11`: التأكد أن القاعدة المفعّلة عبر الهوك **لا يحررها الـ Watchdog** عندما يعيد `GetAsyncKeyState` صفرًا في وضع `hold`.
    3. اختبار `wait_for_modifiers_release` و `simulate_paste` (إرجاع `False` عند فشل `SendInput` دون مسار `keybd_event` كاذب) وحساب `_reposition` عند `3840×2160` وتكبير `2.25`.
- **[T-P0-01] توحيد طبقة النظام في `win32_api.py` (`CB-04`, `OV-04`):**
  - تجميع هياكل `INPUT` (40 بايت)، `DROPFILES`، `KBDLLHOOKSTRUCT`، `MONITORINFO` وكافة تواقيع `argtypes/restype` لدوال `user32` (`GetWindowLongPtrW`/`SetWindowLongPtrW`/`SendInput`/`SetWindowsHookExW`) و `kernel32` (`OpenProcess`/`QueryFullProcessImageNameW`/`CreateEventW`) و `shcore` مع `WinDLL(..., use_last_error=True)` واستخدام `ctypes.get_last_error()`.
- **[T-P0-02] إصلاح `HK-11` و `HK-12` وآلية المسبار السحري للهوك (`A1`, `A2`, `A5`, `HK-01`, `HK-07`):**
  1. **ملكية الهوك (`A1-أ`):** في `_watchdog_loop`، القواعد ذات `activated_by_hook == True` تُستثنى تماماً من تحرير `not physically_down`؛ يحررها الهوك وحده عند `KeyUp` (أو سقف المدة / إعادة التركيب).
  2. **التتبع الفيزيائي والكبت المتماثل (`A1-ب`, `A5`, `R10`):** يحتفظ الهوك بـ `_phys_down: set[int]` (يُحدَّث لكل حدث غير محقون وتستشيره `wait_for_modifiers_release`) وبـ `_suppressed_down: set[int]` لضمان بلع `KeyUp` لأي مفتاح بُلع في `KeyDown` حتى لو تغيّرت `rule.is_active`.
  3. **فحص التركيب ومسبار النبض الذاتي (`A2`):**
     - تفحص `start()` نجاح `self._hook_handle` وتُرجع `bool` مع تسجيل `get_last_error()` عند الفشل.
     - كل `HOOK_PROBE_INTERVAL_SEC = 2.0` (في حالة الخمول فقط): يرسل الـ Watchdog عبر `SendInput` حدث `KEYUP` للمفتاح المحايد `VK_NONAME (0xFC)` مع `dwExtraInfo = 0x41475956` (`"AGYV"`).
     - في `_low_level_proc`: عند رؤية `vk == 0xFC and dwExtraInfo == 0x41475956` يُحدَّث `_last_probe_ack = time.monotonic()` ويعاد `1` فوراً.
     - عند غياب استجابة المسبار لدورتين (`> 4.5s`) أو موت خيط الهوك: يُرسل `WM_QUIT`، يُلغى الهوك القديم، تُصفَّر `_phys_down` و `_suppressed_down`، ويُعاد تشغيل خيط الهوك مع `logger.warning`.
- **[T-P0-03] الصدق الحتمي لنتيجة اللصق وإلغاء `keybd_event` (`A3`, `EN-01`, `CB-02`, `HK-03`):**
  - حذف `keybd_event` fallback نهائياً من `simulate_paste` و `simulate_enter` (`A3`).
  - جعل `wait_for_modifiers_release` يفحص `GetAsyncKeyState` + `_phys_down` (`R10`) ويعيد `bool`؛ إذا انتهت المهلة (`450ms`) والمستخدم لا يزال ضاغطاً على `Ctrl` تعيد `simulate_paste` القيمة `False` دون إرسال `V` عارٍ.
  - عند `GetForegroundWindow() == 0` لحظة الإنهاء (`UAC`/`Win+L`): يُحفظ الملف دون محاولة لصق، وفي `engine._finish_recording` لا تظهر `"⚡ تم اللصق!"` إلا عند عودة `True` فعلياً، وإلا تظهر `"💾 حُفظ (الصق بـ Ctrl+V)"` مع `logger.warning`.
- **[T-P0-04] التحقق الصارم من الاختصارات والإعدادات والدمج العميق (`CF-01`, `CF-02`, `CF-04`, `CF-05`, `HK-02`, `R4`):**
  - توسيع `VK_MAP` ليشمل `A-Z` و `0-9`، ورفض أي رمز مجهول بـ `ValueError` يلتقطه المحرك بتحذير ويعود للافتراضي الآمن.
  - فحص حصرية المعدِّلات (`strict_modifiers: true`) لمنع ابتلاع `Ctrl+F9` و `Shift+F10`.
  - توحيد كافة القيم الافتراضية في `dataclass` واحد داخل `config.py` دون إنشاء مجلدات داخل `load()` (`TS-03`)، وعدم توسيع `~` عند `save()`، وتنفيذ `_deep_merge` لقراءة `config.local.json` الاختياري (`R4`).

---

### 🟡 المرحلة P1 — الاعتمادية، حماية المستكشف، طابور الواجهة، والإيقاف الرشيق

- **[T-P1-01] إزالة ابتلاع الأخطاء وحماية الكبسولة و `ffmpeg` (`HK-04`, `AR-01`, `AR-02`):**
  - استبدال `except Exception: pass` بـ `logger.exception`/`logger.warning`، وإحاطة `_finish_recording` بـ `try...finally` يضمن عدم تعليق الكبسولة.
  - التقاط `stderr` لـ `ffmpeg` وتسجيل سبب الفشل وحذف أي ملف `.m4a` جزئي تالف عند الفشل أو `TimeoutExpired`، وتسجيل تحذير عند `status` غير فارغ في `_audio_callback`.
- **[T-P1-02] حماية المستكشف Fail-Open وطابور الواجهة وترتيب الإقلاع (`CB-01`, `OV-01`, `OV-02`, `R5`, `R7`):**
  - قراءة اسم العملية الهدف بـ `PROCESS_QUERY_LIMITED_INFORMATION` + `QueryFullProcessImageNameW` مع سياسة **Fail-Open** (`R5`)، وتخطّي اللصق التلقائي في `blocked_paste_processes` (افتراضياً `["explorer.exe", "SearchHost.exe", "ShellExperienceHost.exe"]`).
  - تهيئة `overlay.init_ui()` قبل `listener.start()` (`OV-02`)، واستخدام `SimpleQueue` يستطلعه خيط `Tkinter` كل `UI_IDLE_POLL_MS = 50` (`R7`).
- **[T-P1-03] حدث الإيقاف الرشيق وديناميكية السكربتات (`RP-01`, `REL-02`, `REL-03`, `DOC-01`, `R8`):**
  - إنشاء حدث ويندوز مسمى `Local\AntigravityVoiceEngine_Shutdown` يستمع له المحرك للإغلاق النظيف.
  - إنشاء `stop_voice.bat` وتحديث `uninstall_startup.bat` لإرسال الحدث عبر PowerShell القياسي `[System.Threading.EventWaitHandle]::OpenExisting("Local\AntigravityVoiceEngine_Shutdown").Set()` (`R8`) مع fallback لمسار `"%~dp0main.py"`, واكتشاف Python 3.10+ عبر `pyw.exe` أولاً، وتحديث `README.md`.
- **[T-P1-04] تدوير السجلات والخصوصية ودقة التوقيت (`SEC-01`, `REL-01`, `AR-05`, `HK-05`):**
  - `RotatingFileHandler` (`1MB × 2`) مع fallback لـ `NullHandler`، وتسجيل اسم البرنامج التنفيذي للنافذة فقط افتراضياً، واعتماد `time.monotonic()` و `kb.time`.

---

### 🟢 المرحلة P2 — تثبيت التبعيات ومصفوفة GitHub Actions CI (`R2`, `R3`, `TS-01`)

- **[T-P2-01] تقييد التبعيات وعزل اختبارات العتاد (`R3`, `TS-02`, `TS-07`):**
  - تحديث `requirements.txt` بنطاقات متوافقة محددة السقف وإضافة `requirements-dev.txt` بإصدار `pytest` مثبّت (`R3`).
  - حفظ/استعادة الحافظة في اختبار الحافظة الحقيقي، ووسم اختبارات العتاد الفيزيائي بـ `@pytest.mark.hw` مع تشغيل كافة اختبارات الوحدة واختبارات Win32 المعزولة في السحابة.
- **[T-P2-02] إعداد `.github/workflows/ci.yml` بمصفوفة بايثون (`R2`):**
  - تشغيل الاختبارات على `windows-latest` عبر مصفوفة `python-version: ["3.10", "3.11", "3.12", "3.13"]` لإثبات التوافق الكامل بالبرهان الأخضر.
