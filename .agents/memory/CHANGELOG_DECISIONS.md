# 📝 سجل القرارات والتغييرات البرمجية (CHANGELOG_DECISIONS.md)

## إصدار v2.1.1 — إغلاق حالات حافة نظام التشغيل (V21-01 إلى V21-05)

### 1. المشكلة التي حُلت:
- **V21-01 (Secure Desktop / Win+L / UAC Orphan Reaper):** عند قفل الشاشة بـ `Win+L` أو ظهور موجه `UAC` أثناء الضغط على الهوك، يتوقف نظام ويندوز عن إرسال أحداث `KeyUp` للـ Hook. كان التسجيل يظل محبوساً لأن الـ Watchdog لا يفك الهوك تلقائياً.
- **V21-02 (UIPI Probe SendInput Block):** عند تواجد النافذة النشطة بصلاحيات مسؤول (Elevated/Admin)، تحجب حماية UIPI إدخال المسبار الاصطناعي (`SendInput == 0`) مما كان يتسبب في اشتباه كاذب بسقوط الهوك وإعادة تنصيبه كل 4.5 ثانية.
- **V21-03 (Hook Thread Handle Cleanup Isolation):** كان ثريد الهوك القديم قد يفك مقبض الهوك الجديد في حال حدوث سباق (Race Condition) مع `_reinstall_hook`.
- **V21-04 (Graceful Stop Wait):** استبدال مهلة الـ 900ms الثابتة في `stop_voice.bat` بانتظار ذكي حتى 10 ثوانٍ (`WaitForExit(10000)`).
- **V21-05 (Reinstall Backoff):** تقييد محاولات إعادة تنصيب الهوك المتكررة بفاصل أدنى 5 ثوانٍ (`HOOK_REINSTALL_BACKOFF_SEC`).

### 2. الملفات المعدلة:
- `win32_api.py`: إضافة `OpenInputDesktop` و `CloseDesktop` و `is_input_desktop_accessible()`.
- `hotkey_listener.py`: إضافة فحص سطح المكتب المقفل، ومؤقت أمان انتهاء صلاحية المفتاح المعلق (`orphan_timeout_sec`)، وتحديث Ack عند حجب UIPI، وعزل مقبض الهوك محلياً في الثريد، وحد أدنى 5 ثوانٍ للـ Backoff.
- `engine.py`: ربط `orphan_timeout_sec` بـ `max_recording_duration_sec + 5.0`.
- `stop_voice.bat`: استخدام `WaitForExit(10000)` قبل الإنهاء الإجباري، واستبدال timeout بـ ping لتفادي أخطاء redirection.
- `tests/test_p1_reliability.py`: إضافة 4 اختبارات معزولة بنسبة 100% لتغطية سيناريوهات V21-01 و V21-02 و V21-05.

### 3. الدرس المستفاد:
- في بيئة Windows Win32، أي LL Hook (`WH_KEYBOARD_LL`) لا يستقبل أحداث لوحة المفاتيح أثناء شاشات الأمان العالي (`OpenInputDesktop == NULL`). لا بد دائماً من وجود Companion Watchdog يفحص سلامة سطح المكتب وحاصد للأيتام (Orphan Reaper) لفك التعليق.
- دوال `SendInput` تفشل حتماً مع نوافذ الـ Admin بدون صلاحيات مرتفعة، لذا لا يجب أبداً اعتبار فشل `SendInput` دليلاً على موت الهوك.

### 4. المخاطر والآثار الجانبية (Risks & Side Effects):
- **الخطر:** استدعاء `OpenInputDesktop` على ترددات عالية جداً قد يستهلك وقت معالجة طفيف.
- **التخفيف:** يُستدعى فقط في حلقة الـ Watchdog الدورية (كل 35ms)، وهو خفيف جداً (مجرد استعلام مقبض بدون حجز ذاكرة).
