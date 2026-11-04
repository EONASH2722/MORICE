"""Keep Qt's per-pixel glass alpha; Windows acrylic fallback can be opaque."""
import ctypes
import os


def apply_backdrop(window, enabled):
    if os.name!='nt':return 'translucent'
    try:
        api=ctypes.WinDLL('dwmapi')
        api.DwmSetWindowAttribute.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p,ctypes.c_uint]
        api.DwmSetWindowAttribute.restype=ctypes.c_long
        handle=int(window.winId());dark=ctypes.c_int(1)
        api.DwmSetWindowAttribute(handle,20,ctypes.byref(dark),4)
        class Margins(ctypes.Structure):
            _fields_=[('left',ctypes.c_int),('right',ctypes.c_int),('top',ctypes.c_int),('bottom',ctypes.c_int)]
        api.DwmExtendFrameIntoClientArea.argtypes=[ctypes.c_void_p,ctypes.POINTER(Margins)]
        api.DwmExtendFrameIntoClientArea(handle,ctypes.byref(Margins(0,0,0,0)))
        backdrop=ctypes.c_int(1)
        result=api.DwmSetWindowAttribute(handle,38,ctypes.byref(backdrop),4)
        return ('translucent-black' if enabled else 'dark') if result==0 else 'translucent'
    except (OSError,AttributeError):return 'translucent'
