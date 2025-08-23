# Agents Instructions for 0x0 File Hosting Service

## Build/Test/Lint Commands
- **Run tests**: `python -m pytest` (pytest configured in pyproject.toml)
- **Run a single test**: `python -m pytest path/to/test_file.py::TestClass::test_name`
- **Start development server**: `set FLASK_APP=fhost && python -m flask run`
- **Database migration**: `set FLASK_APP=fhost && python -m flask db upgrade`
- **Prune expired files**: `set FLASK_APP=fhost && python -m flask prune`
- **Virus scan**: `set FLASK_APP=fhost && python -m flask vscan`
- **Run moderation UI**: `python mod.py`
- **Test NSFW detection**: `python nsfw_detect.py <file>`

## Architecture
- **Main app**: Flask app in `fhost.py` - file hosting, URL shortening, upload handling
- **Database**: SQLAlchemy models for File, URL, RequestFilter (IP/MIME/UA filtering)
- **Storage**: Files stored by SHA256 hash in `FHOST_STORAGE_PATH` directory
- **Moderation**: TUI interface in `mod.py` using Textual framework in `modui/` package
- **Features**: NSFW detection, virus scanning, file expiration, request filtering

## Code Style & Conventions
- **Imports**: Standard library first, then third-party, then local imports
- **Classes**: PascalCase (File, URL, AddrFilter)
- **Functions**: snake_case (store_file, get_max_lifespan)
- **Constants**: UPPER_CASE in config (FHOST_STORAGE_PATH, MAX_CONTENT_LENGTH)
- **Type hints**: Use typing module, prefer explicit types for function parameters
- **Error handling**: Use Flask's abort() for HTTP errors, try/except for operations
- **Database**: SQLAlchemy declarative models, use db.session for transactions
