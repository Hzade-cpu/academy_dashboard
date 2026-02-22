# Blueprints package
from .auth import auth_bp
from .dashboard import dashboard_bp
from .coaches import coaches_bp
from .analytics import analytics_bp
from .settings import settings_bp
from .leaves import leaves_bp

__all__ = ['auth_bp', 'dashboard_bp', 'coaches_bp', 'analytics_bp', 'settings_bp', 'leaves_bp']
