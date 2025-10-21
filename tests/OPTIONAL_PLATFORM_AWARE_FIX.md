# Optional: Platform-Aware Fix

## Current Fix (Works on all platforms)

The current fix in `stata_mcp_server.py` (lines 209-234) runs on **all platforms** (Mac, Windows, Linux). This is:
- ✓ Safe - works everywhere
- ✓ Simple - no platform detection needed
- ✓ Minimal overhead - ~100ms at startup once

## Platform-Aware Alternative

If you want to **optimize for Windows/Linux** (skip unnecessary initialization), you can make it platform-specific:

```python
# Successfully initialized Stata
has_stata = True
stata_available = True

# Initialize PNG export capability to prevent JVM crash in daemon threads (Mac only)
# This one-time initialization in the main thread ensures all subsequent
# PNG exports in daemon threads will work correctly with _gr_list on
# Windows doesn't need this as its JVM/DLL integration handles daemon threads differently
import platform
if platform.system() == 'Darwin':  # Mac only
    try:
        from pystata.config import stlib, get_encode_str
        import tempfile

        # Create minimal dataset and graph
        stlib.StataSO_Execute(get_encode_str("qui clear"), False)
        stlib.StataSO_Execute(get_encode_str("qui set obs 2"), False)
        stlib.StataSO_Execute(get_encode_str("qui gen x=1"), False)
        stlib.StataSO_Execute(get_encode_str("qui twoway scatter x x, name(_init, replace)"), False)

        # Export to PNG to initialize JVM properly in main thread
        # This prevents SIGBUS crash in daemon threads on Mac
        png_init = os.path.join(tempfile.gettempdir(), "_stata_png_init.png")
        stlib.StataSO_Execute(get_encode_str(f'qui graph export "{png_init}", name(_init) replace width(10) height(10)'), False)
        stlib.StataSO_Execute(get_encode_str("qui graph drop _init"), False)

        # Cleanup
        if os.path.exists(png_init):
            os.unlink(png_init)

        logging.debug("PNG export initialized successfully (Mac-specific JVM fix)")
    except Exception as png_init_error:
        # Non-fatal: log but continue - PNG may still work
        logging.warning(f"PNG initialization failed (non-fatal): {str(png_init_error)}")
else:
    logging.debug("PNG initialization skipped (not needed on non-Mac platforms)")

return True
```

## Recommendation

**Use the current fix (no platform detection)** because:

1. **Overhead is negligible** - ~100ms once at startup, regardless of platform
2. **Simpler code** - No platform-specific logic to maintain
3. **Safer** - Works the same way everywhere
4. **Future-proof** - If Windows/Linux ever have similar issues, they're already fixed

Only use platform-aware version if:
- You have strict performance requirements at startup
- You want to minimize any JVM interaction on Windows/Linux
- You need different behavior per platform

## Testing

If you implement platform-aware version, test on:
- ✓ Mac - should initialize PNG and work
- ✓ Windows - should skip initialization and still work
- ✓ Linux - should skip initialization and work (if supported)
