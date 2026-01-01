from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from jinja2 import Environment, FileSystemLoader
from starlette_babel.contrib.jinja import configure_jinja_env

from airbeeps.config import TEMPLATE_DIR, settings

__all__ = ["BabelConnectionConfig", "MessageSchema", "MessageType", "get_sender"]


class BabelConnectionConfig(ConnectionConfig):
    def template_engine(self) -> Environment:
        """
        Return template environment
        """
        folder = self.TEMPLATE_FOLDER
        if not folder:
            raise ValueError(
                "Class initialization did not include a ``TEMPLATE_FOLDER`` ``PathLike`` object."
            )
        template_env = Environment(loader=FileSystemLoader(folder), autoescape=True)
        configure_jinja_env(template_env)
        return template_env


# Lazy initialization to avoid startup crash when MAIL_SERVER is empty
_sender: FastMail | None = None


def get_sender() -> FastMail:
    """Get mail sender instance (lazy initialization)."""
    global _sender
    if _sender is None:
        if not settings.MAIL_SERVER:
            raise RuntimeError(
                "Mail is not configured. Set AIRBEEPS_MAIL_SERVER environment variable."
            )
        conf = BabelConnectionConfig(
            MAIL_USERNAME=settings.MAIL_USERNAME,
            MAIL_PASSWORD=settings.MAIL_PASSWORD,
            MAIL_PORT=settings.MAIL_PORT,
            MAIL_SERVER=settings.MAIL_SERVER,
            MAIL_STARTTLS=settings.MAIL_STARTTLS,
            MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
            MAIL_FROM=settings.MAIL_FROM,
            TEMPLATE_FOLDER=TEMPLATE_DIR,
            USE_CREDENTIALS=True,
            VALIDATE_CERTS=True,
        )
        _sender = FastMail(conf)
    return _sender
