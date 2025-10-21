# Mac-Specific PNG Export Hang - Root Cause Analysis

## The Discovery

When running PNG export in a daemon thread on Mac in a **completely fresh Python process**, we don't just get a hang - we get a **JVM crash**:

```
# A fatal error has been detected by the Java Runtime Environment:
#
#  SIGBUS (0xa) at pc=0x00000001285cb7c0, pid=59795, tid=4367
#
# JRE version:  (21.0.8+9)
# Java VM: OpenJDK 64-Bit Server VM
# Problematic frame:
# V  [libjvm.dylib+0x4637c0]  CodeHeap::allocate(unsigned long)+0x1a4
```

## Root Cause

### Stata's Graphics Architecture

1. **Stata uses embedded JVM for graphics** on all platforms
   - PyStata config.py line ~200: `_add_java_home_to_path()`
   - Java handles PNG/SVG/PDF export rendering
   - `javahome = sfi.Macro.getGlobal('c(java_home)')`

### Why Mac Is Different

#### Mac-Specific Issues:

1. **JVM Thread Attachment on Mac**
   - On Mac, the JVM may require special handling for non-main threads
   - Daemon threads in Python may not properly attach to JVM
   - The JVM expects to be initialized from the main thread

2. **Memory Allocation in Daemon Threads**
   - Error: `CodeHeap::allocate(unsigned long)+0x1a4`
   - The JVM's code heap allocation fails in daemon threads
   - This is likely a thread-local storage (TLS) issue on Mac

3. **Platform-Specific libstata Behavior**
   - Mac: `libstata-mp.dylib` (Darwin-specific build)
   - Windows: `stata-mp-64.dll` (Windows-specific build)
   - Different JVM integration paths per platform

#### Why Windows Works:

1. **Windows Threading Model**
   - Windows DLLs handle thread attachment differently
   - JVM on Windows may be more permissive with thread creation
   - Different JNI (Java Native Interface) initialization

2. **Different Graphics Subsystem**
   - Windows: Uses GDI/Direct2D through Java
   - Mac: Uses CoreGraphics/Quartz through Java
   - Mac's graphics frameworks may have stricter thread requirements

## Timeline of Behavior

### Fresh Python Process (First Run)
```python
# Fresh process, daemon thread, no PNG initialization
result: JVM CRASH (SIGBUS)
```

### After First PNG in Main Thread
```python
# Main thread PNG export initializes JVM properly
result: SUCCESS

# Then daemon thread PNG export
result: SUCCESS (JVM already initialized)
```

### After Multiple Test Runs
```python
# If JVM was initialized earlier in the session
result: SUCCESS (appears to "work")
```

This explains why:
- Your verification tests passed (JVM was initialized in main thread first)
- MCP server hangs on first run (daemon thread tries to initialize JVM)
- Running PDF then PNG works (PDF initializes JVM)
- Windows doesn't have this issue (different JVM/threading model)

## The Fix Analysis

### Why One-Time Initialization Works

```python
# At server startup (main thread):
stlib.StataSO_Execute(get_encode_str("qui clear"), False)
stlib.StataSO_Execute(get_encode_str("qui set obs 2"), False)
stlib.StataSO_Execute(get_encode_str("qui gen x=1"), False)
stlib.StataSO_Execute(get_encode_str("qui twoway scatter x x, name(_init, replace)"), False)
# This initializes JVM in main thread ↓
stlib.StataSO_Execute(get_encode_str(f'qui graph export "{png_init}", name(_init) replace'), False)
```

**What this does:**
1. Forces JVM initialization in **main thread** (not daemon)
2. Attaches JVM to the Python process properly
3. Allocates JVM code heap in main thread context
4. All subsequent daemon thread calls reuse initialized JVM

**Why it prevents crashes:**
- JVM is already running and properly attached
- Daemon threads don't need to initialize JVM
- They just use the existing JVM instance
- Thread attachment happens correctly

## Platform Comparison

| Aspect | Mac (Darwin) | Windows |
|--------|--------------|---------|
| **Library** | libstata-mp.dylib | stata-mp-64.dll |
| **JVM Integration** | Stricter thread requirements | More permissive |
| **Graphics Backend** | Java → CoreGraphics/Quartz | Java → GDI/Direct2D |
| **Daemon Thread PNG** | Crashes without init | Works |
| **Special Config** | `KMP_DUPLICATE_LIB_OK='True'` (line 118) | Standard |
| **Thread Model** | POSIX threads (pthread) | Windows native threads |

## Evidence

### From Test Results:

1. **test_fresh_session_hang.py** (isolated process):
   - Result: **JVM CRASH** (not just hang)
   - Proves JVM initialization issue

2. **test_one_time_init_fix.py** (with initialization):
   - Result: **ALL SUCCESS**
   - Proves fix works

3. **test_mac_specific_investigation.py** (after init):
   - Result: **ALL SUCCESS** (daemon threads work after main thread init)
   - Proves JVM reuse works

### From PyStata Code:

1. **config.py lines 117-118** (Mac-specific):
   ```python
   if os_system == 'Darwin':
       os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
   ```
   Mac requires special Intel MKL (Math Kernel Library) configuration

2. **config.py ~line 200**:
   ```python
   _add_java_home_to_path()
   ```
   Stata explicitly manages Java integration

## Conclusion

This is **NOT a simple threading bug** - it's a **Mac-specific JVM initialization issue** in Stata's graphics subsystem:

1. **Root Cause**: JVM cannot be initialized from daemon threads on Mac when used through libstata-mp.dylib
2. **Symptom**: SIGBUS crash in `CodeHeap::allocate()` during first PNG export in daemon thread
3. **Why Mac Only**: Different JVM integration, threading model, and graphics frameworks compared to Windows
4. **Why Fix Works**: One-time PNG export in main thread initializes JVM properly, allowing daemon threads to reuse it
5. **Windows Difference**: Windows JVM/DLL architecture allows daemon thread initialization

The fix is **absolutely necessary for Mac** and **harmless for Windows** (just redundant initialization).

## Recommendations

1. **Keep the fix** - It's Mac-specific but doesn't hurt Windows
2. **Add platform detection** (optional) - Could skip initialization on Windows for minimal optimization
3. **Document the issue** - Help future developers understand this Mac quirk
4. **Consider reporting to StataCorp** - This may be a bug in libstata-mp.dylib's JVM integration

## Alternative Solutions Considered

1. ❌ **Use non-daemon threads** - Would prevent timeout/cancellation in MCP server
2. ❌ **Disable PNG export** - Defeats the purpose
3. ❌ **Manual initialization per do-file** - Too costly with large datasets (preserve/restore)
4. ✓ **One-time PNG initialization at startup** - Solves the problem with minimal overhead
