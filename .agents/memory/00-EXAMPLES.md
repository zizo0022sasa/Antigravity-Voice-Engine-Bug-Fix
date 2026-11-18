# 🏛️ الأنماط القياسية المعتمدة (00-EXAMPLES.md)

## نمط: فحص قفل سطح مكتب ويندوز والتعافي من حجب الهوك (Secure Desktop Check)

```python
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
GENERIC_READ = 0x80000000

user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
user32.OpenInputDesktop.restype = wintypes.HANDLE
user32.CloseDesktop.argtypes = [wintypes.HANDLE]
user32.CloseDesktop.restype = wintypes.BOOL

def is_input_desktop_accessible() -> bool:
    """
    Returns False when Windows is on the Secure Desktop (Win+L Lock Screen or UAC prompt),
    where WH_KEYBOARD_LL hooks do not receive KeyUp events.
    """
    try:
        hdesk = user32.OpenInputDesktop(0, False, GENERIC_READ)
        if not hdesk:
            return False
        user32.CloseDesktop(hdesk)
        return True
    except Exception:
        return True
```
