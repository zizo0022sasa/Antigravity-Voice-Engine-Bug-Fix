# 🗺️ الخطة الهندسية الشاملة للإصدار v2.1 (PLAN.md)

- **حالة التنفيذ:** 🔒 **مُجمَّد برمجياً (`PLAN-ONLY / ZERO CODE TOUCHED`)** — بانتظار مراجعة واعتماد الوكيل الخارجي والمالك.
- **الدستور الحاكم:** [`.agents/rules/00-architecture-governance.md`](../.agents/rules/00-architecture-governance.md) (صفر تفريغ خارجي STT/Whisper/API — تسجيل محلي وإلقاء ملف `.m4a` عبر `CF_HDROP` فقط).

---

## 🏛️ الركائز الهندسية للخطة (مرونة · ديناميكية · بساطة · قابلية صيانة)

1. **مصدر حقيقة واحد بدون تكرار (`DRY & Single Source of Truth`):**
   - كل القيم الافتراضية تعيش في تعريف `dataclass` داخل `config.py` فقط (إلغاء أي تكرار في `load()`).
   - كل هياكل وتواقيع Win32 64-bit تعيش في `win32_api.py` بـ `WinDLL(..., use_last_error=True)` مرة واحدة لكل المشروع.
2. **ديناميكية كاملة بلا قيم صلبة (`100% Dynamic`):**
   - اكتشاف `pythonw.exe` ديناميكياً في السكربتات عبر `pyw.exe` القياسي لويندوز ثم `where pythonw.exe` ثم `%LOCALAPPDATA%\Programs\Python\Python*\pythonw.exe` (يعمل على Python 3.10 / 3.11 / 3.12 / 3.13+ تلقائياً).
   - دعم `config.local.json` الاختياري لتخصيص أي إعداد محلياً دون لمس `config.json` المتتبع.
   - قوائم `blocked_paste_processes` و `allowed_paste_processes` و `strict_modifiers` و `auto_send_enter_delay_ms` ديناميكية بالكامل من الإعدادات.
3. **صفر تعقيد زائد (`Zero Over-Engineering`):**
   - لا سيرفرات داخلية، لا Sockets، لا مكتبات إضافية، ولا أنابيب `ffmpeg stdin` قابلة للتجميد؛ معمارية خفيفة حتمية وسهلة القراءة والصيانة.
4. **سقف حجم صارم (`< 9.5KB` لكل ملف `.py`):**
   - يُفرض باختبار آلي في `pytest` لضمان بقاء كل وحدة صغيرة ومقروءة بالكامل 100% لدى أي أداة مراجعة خارجية.

---

## 🛠️ مراحل التنفيذ المقسمة (عند صدور أمر البدء فقط)

### 🔴 المرحلة P0 — البنية المعيارية، الهوك الذاتي التعافي، وشفافية اللصق
- **[T-P0-01] تأسيس `win32_api.py` وضبط سقف الملفات (`< 9.5KB`):**
  - تجميع هياكل `INPUT` (40 بايت)، `DROPFILES`، `KBDLLHOOKSTRUCT`، `MONITORINFO` وتواقيع دوال `user32` / `kernel32` / `shcore` مع `use_last_error=True` (حل `CB-04`, `OV-04`, وتخفيض حجم `hotkey_listener.py`, `clipboard_injector.py`, و `overlay.py` تحت `9.5KB`).
- **[T-P0-02] الهوك الذاتي التعافي وحارس شاشة القفل (`HK-01`, `HK-03`, `HK-07`):**
  - تسجيل `ctypes.get_last_error()` فور فشل `SetWindowsHookExW` وإتاحة خاصية `hook_alive`.
  - فحص صحة الهوك كل ثانية وإعادة تشغيل خيط الهوك تلقائياً إذا سقط أو انتهت حلقة `GetMessageW`.
  - عند `GetForegroundWindow() == 0` (شاشة `UAC` أو `Win+L`) أثناء التسجيل: حفظ التسجيل بأمان دون محاولة لصق فاشلة.
- **[T-P0-03] الصدق الحتمي لنتيجة اللصق ومنع السباق المتبقي (`EN-01`, `CB-02`):**
  - تعديل `wait_for_modifiers_release` ليعيد `bool` (`True` إذا رُفعت الأصابع، `False` إذا انتهت المهلة وأصابع المستخدم لا تزال ضاغطة على `Ctrl`)؛ عند `False` تتوقف `simulate_paste` وتُرجع `False` فوراً بدلاً من إرسال `V` عارٍ.
  - في `engine._finish_recording`: فحص عائد `simulate_paste`؛ عرض `"⚡ تم اللصق!"` فقط عند `True`، وعرض `"💾 حُفظ (الصق بـ Ctrl+V)"` مع `logger.warning` عند `False`.
- **[T-P0-04] التحقق الديناميكي الصارم من الاختصارات والإعدادات (`CF-01`, `CF-02`, `CF-04`, `CF-05`, `HK-02`):**
  - إضافة الحروف `A-Z` والأرقام `0-9` إلى `VK_MAP`، ورفض أي رمز غير معروف بـ `ValueError` يلتقطه المحرك بتحذير ويعود للافتراضي الآمن بدلاً من إسقاط الرمز بصمت.
  - تفعيل حصرية المعدِّلات (`strict_modifiers=True` افتراضياً) لمنع ابتلاع `Ctrl+F9` و `Shift+F10`.
  - التحقق من صلاحية `mode`, `audio_format`, `position`, `sample_rate`, `channels` في `EngineConfig.load()`، وتوحيد الافتراضيات من `dataclass` واحد، ودعم دمج `config.local.json` دون توسيع `~` عند الحفظ.

---

### 🟡 المرحلة P1 — الاعتمادية، منع التعارض، والإيقاف الرشيق
- **[T-P1-01] إزالة ابتلاع الأخطاء وحماية الكبسولة والملفات (`HK-04`, `AR-01`, `AR-02`):**
  - استبدال `except Exception: pass` بـ `logger.exception` / `logger.debug`، وإحاطة `_finish_recording` بـ `try...finally` يضمن إخفاء الكبسولة لو وقع خطأ.
  - التقاط `stderr` لـ `ffmpeg` عند الفشل أو `TimeoutExpired` وتسجيل تحذير واضح وحذف أي ملف `.m4a` جزئي تالف، وتسجيل تحذير عند `status` غير فارغ في المايك.
- **[T-P1-02] حماية المستكشف وطابور الواجهة وترتيب الإقلاع (`CB-01`, `OV-01`, `OV-02`):**
  - فحص اسم العملية للنافذة الأمامية (`QueryFullProcessImageNameW`): تخطّي إرسال `Ctrl+V` إذا كانت ضمن `blocked_paste_processes` (مثل `explorer.exe`) أو خارج `allowed_paste_processes` (إن حُددت)، مع حفظ الملف وبقائه جاهزاً في الحافظة.
  - تهيئة `overlay.init_ui()` قبل `listener.start()`، وتمرير أوامر الواجهة عبر `SimpleQueue` يقرأه خيط `Tkinter` كل `25ms` بدلاً من استدعاء `root.after` عبر الخيوط.
- **[T-P1-03] الإيقاف الرشيق وديناميكية السكربتات (`RP-01`, `REL-02`, `REL-03`, `SEC-07`, `DOC-01`):**
  - إضافة حدث ويندوز مسمى `Local\AntigravityVoiceEngine_Shutdown` يستمع له المحرك ليُغلق المايك والهوك والكبسولة بنظافة تامة دون `Stop-Process -Force`.
  - إضافة `stop_voice.bat` وتحديث `uninstall_startup.bat` و `install_startup.bat` و `start_voice_silent.vbs` لاكتشاف Python 3.10+ ديناميكياً وإرسال حدث الإيقاف الرشيق، ومزامنة `README.md`.
- **[T-P1-04] تدوير السجلات والخصوصية ودقة التوقيت (`SEC-01`, `REL-01`, `AR-05`, `HK-05`):**
  - اعتماد `RotatingFileHandler` (`1MB × 2`) مع fallback آمن عند عدم قابلية الكتابة، وتسجيل اسم البرنامج التنفيذي بدلاً من عناوين النوافذ الكاملة افتراضياً، واستخدام `time.monotonic()` و `kb.time` لدقة التوقيت.

---

### 🟢 المرحلة P2 — الاختبارات المعزولة و GitHub Actions CI
- **[T-P2-01] عزل الاختبارات عن جهاز المطور (`TS-02`, `TS-03`, `TS-07`):**
  - حفظ واستعادة الحافظة في اختبار الحافظة، وعدم إنشاء مجلدات خارج `tmp_path`، واستخدام Mocks للصوت عند عدم توفر مايك في السحابة.
- **[T-P2-02] اختبارات الوحدة الشاملة للإصلاحات (`TS-04..08`):**
  - اختبار `_low_level_proc` مباشرة بـ `KBDLLHOOKSTRUCT` (بلع `F10`، حصرية المعدِّلات، تجاهل `LLKHF_INJECTED`، الـ Auto-repeat).
  - اختبار `wait_for_modifiers_release`، وفشل `simulate_paste` (`EN-01`)، وحظر `explorer.exe` (`CB-01`)، وإعادة تركيب الهوك (`HK-01`)، وحساب الـ 4K (`scale=2.25`)، واختبار معماري يفشل إذا تجاوز أي ملف `.py` سقف `9.5KB`!
- **[T-P2-03] إعداد `.github/workflows/ci.yml` + `requirements-dev.txt`:**
  - تشغيل كافة الاختبارات آلياً على `windows-latest` (Python 3.12) لإثبات النجاح بالبرهان السحابي الأخضر.
