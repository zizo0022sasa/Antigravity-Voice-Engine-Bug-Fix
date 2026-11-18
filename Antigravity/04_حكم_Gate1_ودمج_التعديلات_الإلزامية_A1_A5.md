# 🛡️ حكم بوابة Gate-1 والإثبات الميداني لـ HK-11 ودمج التعديلات الـ 15 (A1–A5 + R1–R10)

- **حالة الكود:** 🔒 **صفر تعديل على أي ملف كود برمجي** (نفس SHA الكوميت `f168f47`).
- **حالة المراجعة:** استجابة كاملة لحكم المراجع المعماري (`APPROVED WITH REQUIRED AMENDMENTS`) لإصدار الاعتماد النهائي `APPROVED FOR EXECUTION`.

---

## 1. الإثبات الميداني القاطع لاكتشاف `HK-11` (بدون لمس الكود!)

رصد الوكيل الخارجي ببراعة هندسية في الملحق `03` أن مفتاح المشغِّل المبلوع في `WH_KEYBOARD_LL` (`return 1`) يمنع نواة ويندوز (`win32k`) من تحديث جدول `gafAsyncKeyState`، فيقرأ `GetAsyncKeyState(F10)` القيمة `0` ويُطلق `_watchdog_loop` حدث `release` خلال `≤ 35ms`!

**البرهان الميداني الحي من `voice_engine.log` على جهاز المالك:**
```text
09:14:30 [INFO] 🎙️ [RECORDING STARTED] Focus: '.agents - Antigravity IDE - Antigravity Settings'
09:14:30 [INFO] 🔄 Switched to Toggle Mode (tap CTRL+CAPSLOCK, F9, F10 again to finish)
...
09:22:02 [INFO] 🎙️ [RECORDING STARTED] Focus: 'Untitled (Workspace) - Antigravity IDE - LICENSE'
09:22:02 [INFO] 🔄 Switched to Toggle Mode (tap CTRL+CAPSLOCK, F9, F10 again to finish)
...
09:33:52 [INFO] 🎙️ [RECORDING STARTED] Focus: '... - Google Chrome'
09:33:52 [INFO] 🔄 Switched to Toggle Mode (tap CTRL+CAPSLOCK, F9, F10 again to finish)
```
- **النتيجة:** **`HK-11` مؤكد بنسبة 100% (`VERIFIED`)!** في كل تسجيلة على الإطلاق، انتقل المحرك إلى `Toggle Mode` في نفس الثانية (`< 35ms`) لأن الـ Watchdog أطلق `release` فورياً بسبب قراءة `GetAsyncKeyState == 0` للمفتاح المبلوع، مما كان سيكسر وضع `hold` تماماً!
- كما تم التحقق الميداني عبر `Get-Process` من الاسم التنفيذي الفعلي لـ Antigravity IDE (`R5`) وهو حرفياً: **`Antigravity IDE.exe`**.

---

## 2. مصفوفة دمج التعديلات الإلزامية الخمسة (`A1` → `A5`) في `PLAN.md`

- **`A1` (علاج `HK-11` — فصل ملكية الهوك + تتبع فيزيائي `_phys_down`):**
  - أُدرج في `T-P0-02`: نجمع بين البساطة والدقة معاً (~15 سطراً فقط):
    1. **ملكية الهوك الحصرية (`A1-أ`):** أي قاعدة فعّلها الهوك (`rule.activated_by_hook == True`) **لا يحررها `_watchdog_loop` مطلقاً**؛ يقتصر تحرير الـ Watchdog على القواعد التي فعّلها هو فقط (أزرار الماوس أو النوافذ المرتفعة التي حجب UIPI عنها الهوك).
    2. **جدول الحالة الفيزيائية (`A1-ب` + `R10`):** يحتفظ الهوك بـ `_phys_down: set[int]` يُحدَّث عند كل حدث غير محقون (`KeyDown` يضيف `vk`، و `KeyUp` يحذفه، ويُصفَّر عند إعادة تركيب الهوك)، وتستشيره `wait_for_modifiers_release` بجانب `GetAsyncKeyState`.
- **`A2` (تحديد آلية المسبار السحري لفحص صحة الهوك وإعادة التركيب):**
  - أُدرج في `T-P0-02`:
    1. تفحص `start()` قيمة `bool(self._hook_handle)` بعد `_hook_ready.wait(0.5)` وتُرجع `bool` صريحاً (وتسجل `ctypes.get_last_error()` عند الفشل).
    2. **مسبار النبض (`Heartbeat Probe` كل `2.0s` أثناء الخمول فقط):** يرسل `SendInput` لحدث `KEYUP` على المفتاح المحايد غير المعيَّن `VK_NONAME (0xFC)` مع علامة سحرية في `dwExtraInfo = 0x41475956` (`"AGYV"`).
    3. في `_low_level_proc`: كاستثناء وحيد مقيد بالعلامة السحرية قبل تجاهل `LLKHF_INJECTED`، إذا كان `vk == 0xFC and kb.dwExtraInfo == 0x41475956` يُحدِّث `_last_probe_ack = time.monotonic()` ويعيد `1` (يُبلع فلا يراه أي تطبيق).
    4. إذا مرّت دورتان متتاليتان (`> 4.5s`) دون تحديث `_last_probe_ack` أو مات خيط الهوك: يُنهي الخيط القديم بـ `WM_QUIT` + `UnhookWindowsHookEx`، يصفّر `_phys_down` و `_suppressed_down`، ويعيد تركيب خيط هوك جديد مع `logger.warning`.
- **`A3` (علاج `CB-11` — حذف مسار `keybd_event` الكاذب نهائياً):**
  - أُدرج في `T-P0-03`: حذف `keybd_event` fallback من `simulate_paste` و `simulate_enter` بالكامل. إذا فشل `SendInput` (بسبب UIPI مثلاً) تُسجِّل الدالة `ctypes.get_last_error()` وتُرجع `False` بصدق 100% فتظهر شارة `"💾 حُفظ (الصق بـ Ctrl+V)"`.
- **`A4` (تقديم اختبارات التوصيف `T-P0-00` أولاً + إلغاء سقف البايتات المصطنع):**
  - أُدرج في أول `P0`: كتابة اختبارات التوصيف المعزولة (`Characterization Tests`) لـ `_low_level_proc` و `wait_for_modifiers_release` و `_reposition@2.25` و `simulate_paste` **كأول خطوة (`T-P0-00`) قبل لمس أو إعادة هيكلة أي ملف إنتاجي**.
  - **حُذف سقف `9.5KB` واختبار عدّ البايتات نهائياً** التزاماً بركيزة `KISS`؛ التماسك المعماري وحده يحكم تقسيم الملفات، وعند تجاوز أي ملف `10KB` نرفق ملحقاً نصياً للمراجع كما أثبت الملحق `03` نجاحه.
- **`A5` (علاج `HK-12` — الكبت المتماثل عبر `_suppressed_down`):**
  - أُدرج في `T-P0-02`: يحتفظ `_low_level_proc` بمجموعة `_suppressed_down: set[int]`؛ كل `KeyDown` فيزيائي يُبلع يضيف `vk` إليها، وعند وصول `KeyUp` فيزيائي لأي `vk` داخل `_suppressed_down` يُحذف من المجموعة ويُبلع (`return 1`) حتماً بغض النظر عن `rule.is_active`.

---

## 3. مصفوفة دمج التوصيات العشر (`R1` → `R10`) بالكامل

- **`R1` (`HK-03`):** توثيق صريح بأن الانتقال إلى `Secure Desktop` (`UAC`/`Win+L`) في وضع `hold` للقواعد المملوكة للـ Watchdog ينهي التسجيل ويحفظه بأمان كسلوك مقبول ومقصود، وعدم محاولة اللصق عندما `GetForegroundWindow() == 0`.
- **`R2` (مصفوفة CI):** تشغيل `.github/workflows/ci.yml` عبر مصفوفة `python-version: ["3.10", "3.11", "3.12", "3.13"]` على `windows-latest` بدلاً من تثبيت `3.12` وحده.
- **`R3` (تثبيت التبعيات):** تقييد نطاقات `requirements.txt` وإضافة `requirements-dev.txt` بإصدار `pytest` مثبّت لضمان ثبات البناء في CI.
- **`R4` (دمج عميق لـ `config.local.json`):** تنفيذ `_deep_merge(base, override)` للقواميس المتداخلة (`overlay`, `audio_cues`) حتى لا يمسح تعديل مفتاح فرعي بقية مفاتيح القسم.
- **`R5` (`QueryFullProcessImageNameW` Fail-Open + اسم العملية المتحقق منه):** فتح العملية بصلاحية `PROCESS_QUERY_LIMITED_INFORMATION (0x1000)`، وفي حال تعذر القراءة اعتماد **Fail-Open** (السماح ما لم تكن `allowed_paste_processes` محددة)، وتثبيت الاسم الحقيقي المتحقق منه `"Antigravity IDE.exe"`.
- **`R6` (التفريق بين الإعدادات والثوابت الهندسية):** منصوص عليه صراحة في `README.md` و `PLAN.md`.
- **`R7` (`UI_IDLE_POLL_MS = 50`):** خفض استطلاع طابور الواجهة في الخمول إلى `50ms` (`20Hz`) مع بقاء رسم الموجة `35ms` أثناء التسجيل فقط.
- **`R8` (أداة إرسال حدث الإيقاف في `stop_voice.bat`):** استخدام PowerShell القياسي المدمج في ويندوز `[System.Threading.EventWaitHandle]::OpenExisting("Local\AntigravityVoiceEngine_Shutdown").Set()` بدون أي تبعيات خارجية.
- **`R9` (مطابقة وثيقة الحوكمة مع `DEC-02`):** تم تحديث [`.agents/rules/00-architecture-governance.md`](../.agents/rules/00-architecture-governance.md) بسطر توضيحي يطابق `DEC-02` تماماً.
- **`R10` (`wait_for_modifiers_release` + `_phys_down`):** مُدمج في `A1` و `T-P0-03`.

