"""
Error Handling and Logging System Module
Provides unified error handling, exception logging, and audit logging functionality
"""
import logging
import logging.handlers
import traceback
import sys
from datetime import datetime
from typing import Dict, Any, Optional, Union
from pathlib import Path
from flask import Flask, request, session, jsonify, render_template
from werkzeug.exceptions import HTTPException
import os


class _ColorFormatter(logging.Formatter):
    """Console formatter with ANSI color codes per level."""

    COLORS = {
        'DEBUG':    '\033[36m',   # cyan
        'INFO':     '\033[32m',   # green
        'WARNING':  '\033[33m',   # yellow
        'ERROR':    '\033[31m',   # red
        'CRITICAL': '\033[35m',   # magenta
    }
    RESET = '\033[0m'
    GREY = '\033[90m'

    def format(self, record):
        color = self.COLORS.get(record.levelname, '')
        # Shorten logger name: keep last two segments (e.g. "app.views.administrator" → "administrator")
        name_parts = record.name.split('.')
        short_name = '.'.join(name_parts[-2:]) if len(name_parts) > 1 else record.name
        ts = self.formatTime(record, '%H:%M:%S')
        level_tag = f"{color}{record.levelname:<8}{self.RESET}"
        name_tag = f"{self.GREY}{short_name:<30}{self.RESET}"
        msg = record.getMessage()
        line = f"{ts}  {level_tag}  {name_tag}  {msg}"
        if record.exc_info:
            line += '\n' + self.formatException(record.exc_info)
        return line


class LoggerConfig:
    """Logger configuration"""

    LOG_LEVELS = {
        'DEBUG': logging.DEBUG, 'INFO': logging.INFO,
        'WARNING': logging.WARNING, 'ERROR': logging.ERROR, 'CRITICAL': logging.CRITICAL,
    }

    @staticmethod
    def setup_logging(app: Flask):
        """Configure clean, readable logging."""
        import time
        log_dir = Path(app.config.get('LOG_DIR', 'logs'))
        log_dir.mkdir(exist_ok=True)

        log_level = app.config.get('LOG_LEVEL', 'INFO')
        level = LoggerConfig.LOG_LEVELS.get(log_level.upper(), logging.INFO)

        # ── Root logger ──────────────────────────────────────────────────────
        root = logging.getLogger()
        root.setLevel(level)
        for h in root.handlers[:]:
            root.removeHandler(h)

        # Console: colored, human-readable
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(level)
        console.setFormatter(_ColorFormatter())
        root.addHandler(console)

        # File: plain text, rotating
        file_fmt = logging.Formatter(
            '%(asctime)s  %(levelname)-8s  %(name)s  %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )
        app_file = logging.handlers.RotatingFileHandler(
            log_dir / 'app.log', maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8'
        )
        app_file.setLevel(level)
        app_file.setFormatter(file_fmt)
        root.addHandler(app_file)

        # Errors-only file
        err_file = logging.handlers.RotatingFileHandler(
            log_dir / 'error.log', maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8'
        )
        err_file.setLevel(logging.ERROR)
        err_file.setFormatter(file_fmt)
        root.addHandler(err_file)

        # ── Silence noisy third-party loggers ────────────────────────────────
        # SQLAlchemy raw SQL — shown only if LOG_SQL=true
        sql_level = logging.DEBUG if os.environ.get('LOG_SQL', '').lower() == 'true' else logging.WARNING
        logging.getLogger('sqlalchemy.engine').setLevel(sql_level)
        logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)
        logging.getLogger('sqlalchemy.dialects').setLevel(logging.WARNING)
        # Werkzeug's per-request lines replaced by our after_request hook below
        logging.getLogger('werkzeug').setLevel(logging.WARNING)

        # ── Request logging hooks ─────────────────────────────────────────────
        req_logger = logging.getLogger('repairosapp.request')

        @app.before_request
        def _before():
            request._start_time = time.monotonic()

        @app.after_request
        def _after(response):
            # Skip static assets
            if request.path.startswith('/static'):
                return response
            duration_ms = int((time.monotonic() - getattr(request, '_start_time', time.monotonic())) * 1000)
            status = response.status_code
            user = session.get('username', '-')
            tenant = session.get('current_tenant_name', '-')
            level_fn = req_logger.warning if status >= 400 else req_logger.info
            level_fn(
                f"{request.method} {request.path} → {status}  [{duration_ms}ms]  {user}@{tenant}"
            )
            return response

        app.logger.info("Logging initialised  (SQL=%s)", "on" if sql_level == logging.DEBUG else "off")


class ApplicationError(Exception):
    """Custom application error base class"""

    def __init__(self, message: str, error_code: str = None, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


class ValidationError(ApplicationError):
    """Validation error"""

    def __init__(self, message: str, field: str = None):
        super().__init__(message, 'VALIDATION_ERROR', 400)
        self.field = field


class BusinessLogicError(ApplicationError):
    """Business logic error"""

    def __init__(self, message: str, error_code: str = None):
        super().__init__(message, error_code or 'BUSINESS_ERROR', 422)


class SecurityError(ApplicationError):
    """Security error"""

    def __init__(self, message: str, error_code: str = None):
        super().__init__(message, error_code or 'SECURITY_ERROR', 403)


class DatabaseError(ApplicationError):
    """Database error"""

    def __init__(self, message: str, error_code: str = None):
        super().__init__(message, error_code or 'DATABASE_ERROR', 500)


class ErrorHandler:
    """Error handler"""

    def __init__(self, app: Flask = None):
        self.app = app

        if app:
            self.init_app(app)

    def init_app(self, app: Flask):
        """Initialize the error handler"""
        self.app = app

        # Register error handlers
        app.errorhandler(404)(self.handle_404)
        app.errorhandler(403)(self.handle_403)
        app.errorhandler(401)(self.handle_401)
        app.errorhandler(500)(self.handle_500)
        app.errorhandler(ValidationError)(self.handle_validation_error)
        app.errorhandler(BusinessLogicError)(self.handle_business_error)
        app.errorhandler(SecurityError)(self.handle_security_error)
        app.errorhandler(DatabaseError)(self.handle_database_error)

    def handle_404(self, error):
        """Handle 404 error"""
        if request.path.startswith('/api/'):
            return jsonify({
                'error': 'Resource not found',
                'message': 'The requested resource does not exist',
                'status_code': 404
            }), 404

        return render_template('errors/404.html'), 404

    def handle_403(self, error):
        """Handle 403 error"""
        if request.path.startswith('/api/'):
            return jsonify({
                'error': 'Access forbidden',
                'message': 'Access denied',
                'status_code': 403
            }), 403

        return render_template('errors/403.html'), 403

    def handle_401(self, error):
        """Handle 401 error"""
        if request.path.startswith('/api/'):
            return jsonify({
                'error': 'Unauthorized',
                'message': 'Login required',
                'status_code': 401
            }), 401

        return render_template('auth/login.html'), 401

    def handle_500(self, error):
        """Handle 500 error"""
        self.app.logger.error(f"Internal server error: {error}")

        if request.path.startswith('/api/'):
            return jsonify({
                'error': 'Internal server error',
                'message': 'An internal server error occurred',
                'status_code': 500
            }), 500

        return render_template('errors/500.html'), 500

    def handle_validation_error(self, error: ValidationError):
        """Handle validation error"""
        if request.path.startswith('/api/'):
            return jsonify({
                'error': 'Validation error',
                'message': error.message,
                'field': error.field,
                'status_code': error.status_code
            }), error.status_code

        return render_template('errors/404.html'), error.status_code

    def handle_business_error(self, error: BusinessLogicError):
        """Handle business logic error"""
        if request.path.startswith('/api/'):
            return jsonify({
                'error': 'Business logic error',
                'message': error.message,
                'error_code': error.error_code,
                'status_code': error.status_code
            }), error.status_code

        return render_template('errors/500.html'), error.status_code

    def handle_security_error(self, error: SecurityError):
        """Handle security error"""
        if request.path.startswith('/api/'):
            return jsonify({
                'error': 'Security error',
                'message': error.message,
                'status_code': error.status_code
            }), error.status_code

        return render_template('errors/403.html'), error.status_code

    def handle_database_error(self, error: DatabaseError):
        """Handle database error"""
        self.app.logger.error(f"Database error: {error.message}")

        if request.path.startswith('/api/'):
            return jsonify({
                'error': 'Database error',
                'message': 'Database operation failed',
                'status_code': error.status_code
            }), error.status_code

        return render_template('errors/500.html'), error.status_code
