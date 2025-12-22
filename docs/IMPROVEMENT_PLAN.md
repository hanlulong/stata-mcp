# Stata-MCP Improvement Implementation Plan

**Created:** 2025-12-22
**Status:** DRAFT - Awaiting Review

---

## Overview

This plan covers 5 major improvements to the stata-mcp codebase:

1. **CI/CD Pipeline** - GitHub Actions for automated testing
2. **Server Refactoring** - Break down 4,489-line monolith
3. **Pytest Suite** - Migrate to pytest with better organization
4. **Type Hints** - Complete type coverage
5. **API Documentation** - OpenAPI/Swagger generation

---

## 1. CI/CD Pipeline with GitHub Actions

### Current State
- No `.github/workflows/` directory
- Manual testing only via npm scripts
- Tests require Stata installation (integration tests)

### Implementation Plan

**Step 1.1: Create base workflow structure**
```
.github/
└── workflows/
    ├── ci.yml           # Main CI pipeline (lint, unit tests)
    ├── integration.yml  # Integration tests (manual trigger, needs Stata)
    └── release.yml      # Publish to VS Code marketplace
```

**Step 1.2: ci.yml - Main CI Pipeline**
```yaml
name: CI
on: [push, pull_request]
jobs:
  lint:
    - Python linting (ruff/flake8)
    - TypeScript/JS linting (eslint)

  unit-tests:
    - Run tests that don't require Stata
    - Python unittest discovery
    - Node.js extension tests

  build:
    - Build VS Code extension (vsce package)
    - Verify package integrity
```

**Step 1.3: integration.yml - Integration Tests**
```yaml
name: Integration Tests
on: workflow_dispatch  # Manual trigger only
jobs:
  stata-tests:
    # Requires self-hosted runner with Stata license
    - Full test suite with real Stata
    - Multi-session tests
    - Stop execution tests
```

**Step 1.4: release.yml - Release Pipeline**
```yaml
name: Release
on:
  release:
    types: [published]
jobs:
  publish:
    - Build extension
    - Publish to VS Code Marketplace
    - Publish to Open VSX
```

### Files to Create
| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | Main CI (lint + unit tests) |
| `.github/workflows/integration.yml` | Stata integration tests |
| `.github/workflows/release.yml` | Marketplace publishing |
| `pyproject.toml` | Python project config with ruff settings |

### Estimated Changes
- 4 new files
- ~200 lines of YAML

---

## 2. Server Refactoring (stata_mcp_server.py)

### Current State
- 4,489 lines in single file
- 55 functions/classes
- Multiple concerns mixed together

### Proposed Module Structure

```
src/
├── stata_mcp_server.py     # Main entry point (slimmed to ~500 lines)
├── session_manager.py      # (existing) Multi-session management
├── stata_worker.py         # (existing) Worker process
├── utils.py                # (existing) Path utilities
├── output_filter.py        # NEW: Compact mode filtering (~300 lines)
├── graph_manager.py        # NEW: Graph detection/export (~200 lines)
├── stata_executor.py       # NEW: Core Stata execution (~400 lines)
├── api_models.py           # NEW: Pydantic models (~100 lines)
└── api_routes.py           # NEW: FastAPI route handlers (~600 lines)
```

### Step-by-Step Extraction

**Step 2.1: Extract api_models.py**
- Move all Pydantic models (RunSelectionParams, RunFileParams, ToolRequest, ToolResponse, etc.)
- Move dataclasses and enums
- Estimated: 100 lines

**Step 2.2: Extract output_filter.py**
- Move `apply_compact_mode_filter()` (298 lines)
- Move `check_token_limit_and_save()`
- Move `process_mcp_output()`
- Move all filter-related regex patterns
- Estimated: 350 lines

**Step 2.3: Extract graph_manager.py**
- Move `detect_and_export_graphs()`
- Move `display_graphs_interactive()`
- Move graph-related utilities
- Estimated: 200 lines

**Step 2.4: Extract stata_executor.py**
- Move `run_stata_command()` (296 lines)
- Move `run_stata_selection()`
- Move single-session execution logic
- Keep multi-session routing in main server
- Estimated: 400 lines

**Step 2.5: Extract api_routes.py**
- Move endpoint implementations
- Keep FastAPI app creation in main server
- Use APIRouter for modular routes
- Estimated: 600 lines

**Step 2.6: Slim down stata_mcp_server.py**
- Keep: App initialization, startup/shutdown, main()
- Keep: Global state management
- Keep: CLI argument parsing
- Target: ~500 lines

### Dependency Order
```
utils.py (no deps)
    ↓
api_models.py (no deps)
    ↓
output_filter.py (depends on: utils)
    ↓
graph_manager.py (depends on: utils)
    ↓
stata_executor.py (depends on: output_filter, graph_manager)
    ↓
api_routes.py (depends on: api_models, stata_executor, session_manager)
    ↓
stata_mcp_server.py (imports all, creates app)
```

### Risk Mitigation
- Extract one module at a time
- Run full test suite after each extraction
- Keep backward compatibility for imports
- Use `__all__` exports for clean API

### Estimated Changes
- 5 new files
- ~1,700 lines moved (net reduction in main file)
- Main server: 4,489 → ~500 lines

---

## 3. Pytest Suite Migration

### Current State
- Uses unittest (8 test files, ~1,751 LOC)
- No pytest configuration
- No CI runner

### Implementation Plan

**Step 3.1: Add pytest configuration**
```
pytest.ini          # or pyproject.toml [tool.pytest]
conftest.py         # Shared fixtures
```

**Step 3.2: Create conftest.py with fixtures**
```python
@pytest.fixture
def stata_path():
    return os.environ.get('STATA_PATH', '/Applications/StataNow')

@pytest.fixture
def session_manager(stata_path):
    manager = SessionManager(stata_path=stata_path, ...)
    yield manager
    manager.stop()

@pytest.fixture
def mock_stata():
    # Mock Stata for unit tests that don't need real Stata
    ...
```

**Step 3.3: Convert test files**
| Current File | Action |
|--------------|--------|
| test_session_manager.py | Convert to pytest style |
| test_stop_execution.py | Convert to pytest style |
| test_compact_filter.py | Convert to pytest style |
| test_notifications.py | Convert to pytest style |

**Step 3.4: Add new test categories**
```
tests/
├── conftest.py
├── unit/                    # No Stata required
│   ├── test_output_filter.py
│   ├── test_path_utils.py
│   └── test_api_models.py
├── integration/             # Requires Stata
│   ├── test_session_manager.py
│   ├── test_stop_execution.py
│   └── test_stata_executor.py
└── fixtures/                # .do files and test data
    └── *.do
```

**Step 3.5: Add coverage reporting**
```toml
# pyproject.toml
[tool.coverage.run]
source = ["src"]
omit = ["tests/*"]

[tool.coverage.report]
exclude_lines = ["pragma: no cover", "if TYPE_CHECKING:"]
```

### Files to Create/Modify
| File | Action |
|------|--------|
| `pyproject.toml` | Add pytest and coverage config |
| `tests/conftest.py` | Create shared fixtures |
| `tests/unit/` | New directory for unit tests |
| `tests/integration/` | Rename existing tests |

### Estimated Changes
- 3 new files
- Restructure tests/ directory
- Convert ~1,751 LOC to pytest style

---

## 4. Type Hints Completion

### Current State
- 60-70% coverage
- New code well-typed
- Legacy functions incomplete

### Implementation Plan

**Step 4.1: Add missing return types to stata_mcp_server.py**

Priority functions (no return type hints):
```python
def run_stata_command(command: str, ...) -> str:
def run_stata_file(file_path: str, ...) -> str:
def get_stata_path() -> Optional[str]:
def try_init_stata() -> bool:
```

**Step 4.2: Add parameter type hints**

Missing parameter types:
```python
# Before
def run_stata_file(file_path: str, timeout=600, auto_name_graphs=False, working_dir=None):

# After
def run_stata_file(
    file_path: str,
    timeout: int = 600,
    auto_name_graphs: bool = False,
    working_dir: Optional[str] = None
) -> str:
```

**Step 4.3: Type global variables**

```python
# Before
stata = None
stata_initialized = False

# After
stata: Optional[Any] = None  # pystata.stata module
stata_initialized: bool = False
```

**Step 4.4: Add type stubs or Protocol for PyStata**

```python
from typing import Protocol

class StataProtocol(Protocol):
    def run(self, code: str, echo: bool = True) -> None: ...
    def config(self, splashlog: str, set_streaming: bool) -> None: ...
```

**Step 4.5: Run mypy for validation**

```toml
# pyproject.toml
[tool.mypy]
python_version = "3.9"
warn_return_any = true
warn_unused_ignores = true
ignore_missing_imports = true
```

### Files to Modify
| File | Changes |
|------|---------|
| `stata_mcp_server.py` | Add ~50 type hints |
| `api_routes.py` (after extraction) | Full typing |
| `stata_executor.py` (after extraction) | Full typing |
| `pyproject.toml` | Add mypy config |

### Estimated Changes
- ~100 type hint additions
- 1 new config section

---

## 5. API Documentation (OpenAPI/Swagger)

### Current State
- Good README documentation
- No formal OpenAPI schema
- Endpoint docstrings minimal

### Implementation Plan

**Step 5.1: Add FastAPI metadata**

```python
app = FastAPI(
    title="Stata MCP Server",
    description="MCP server for Stata integration with AI assistants",
    version="0.4.0",
    docs_url="/docs",      # Swagger UI
    redoc_url="/redoc",    # ReDoc
    openapi_url="/openapi.json"
)
```

**Step 5.2: Add endpoint docstrings and tags**

```python
@app.post("/run_selection", tags=["Execution"])
async def run_selection(params: RunSelectionParams) -> Response:
    """
    Execute Stata code selection.

    Args:
        params: Selection parameters including code and optional session_id

    Returns:
        Stata output as plain text

    Raises:
        HTTPException: 500 if Stata execution fails
    """
```

**Step 5.3: Add response models**

```python
class ExecutionResponse(BaseModel):
    output: str = Field(..., description="Stata output text")
    execution_time: float = Field(..., description="Execution time in seconds")
    graphs: List[str] = Field(default_factory=list, description="Generated graph URLs")

class ErrorResponse(BaseModel):
    error: str = Field(..., description="Error message")
    details: Optional[str] = Field(None, description="Additional error details")
```

**Step 5.4: Add API tags for organization**

```python
tags_metadata = [
    {"name": "Execution", "description": "Run Stata code and files"},
    {"name": "Sessions", "description": "Multi-session management"},
    {"name": "Control", "description": "Server control and monitoring"},
    {"name": "Utilities", "description": "Helper endpoints"},
]
```

**Step 5.5: Generate and export OpenAPI schema**

```python
# In main() or as separate script
import json
with open("docs/openapi.json", "w") as f:
    json.dump(app.openapi(), f, indent=2)
```

### Files to Create/Modify
| File | Action |
|------|--------|
| `api_models.py` | Add response models |
| `api_routes.py` | Add docstrings and tags |
| `stata_mcp_server.py` | Add FastAPI metadata |
| `docs/openapi.json` | Generated schema |
| `docs/API.md` | Human-readable API docs |

### Estimated Changes
- ~200 lines of docstrings
- 2 new files (openapi.json, API.md)
- FastAPI metadata additions

---

## Implementation Order

### Phase 1: Foundation (Low Risk)
1. **CI/CD Pipeline** - No code changes, just workflow files
2. **Pytest Migration** - Test infrastructure, parallel to existing tests

### Phase 2: Refactoring (Medium Risk)
3. **Extract api_models.py** - Simple, no logic changes
4. **Extract output_filter.py** - Self-contained, well-tested
5. **Extract graph_manager.py** - Self-contained
6. **Extract stata_executor.py** - Core logic, needs careful testing
7. **Extract api_routes.py** - Final extraction

### Phase 3: Enhancement (Low Risk)
8. **Type Hints** - Incremental, no behavior changes
9. **API Documentation** - Additive only

---

## Rollback Strategy

Each phase will be committed separately:
1. If CI/CD fails → Remove workflow files
2. If refactoring breaks → Git revert to pre-refactor commit
3. If type hints cause issues → They're hints only, remove problematic ones

---

## Success Criteria

| Improvement | Success Metric |
|-------------|----------------|
| CI/CD | All workflows pass on push |
| Refactoring | Main server <600 lines, all tests pass |
| Pytest | pytest runs all tests, coverage >70% |
| Type Hints | mypy passes with no errors |
| API Docs | /docs endpoint shows Swagger UI |

---

## Estimated Effort

| Phase | Files | Lines Changed | Estimated Commits |
|-------|-------|---------------|-------------------|
| CI/CD | 4 | ~200 | 1 |
| Pytest | 5 | ~300 | 1 |
| Refactoring | 6 | ~2,000 | 5-6 |
| Type Hints | 4 | ~150 | 1 |
| API Docs | 4 | ~300 | 1 |
| **Total** | **~15** | **~2,950** | **9-10** |

---

## Review Checklist

Before proceeding, please confirm:

- [ ] CI/CD approach is acceptable (GitHub Actions)
- [ ] Module extraction order makes sense
- [ ] Pytest migration is preferred over keeping unittest
- [ ] Type hints priority is acceptable
- [ ] API documentation scope is sufficient
- [ ] Implementation order is acceptable

---

**Ready for implementation upon approval.**
