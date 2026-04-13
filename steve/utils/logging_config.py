import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def setup_logging(level=logging.INFO):
    """
    Set up centralized logging configuration for the bot.
    Log files rotate daily at midnight, named like bot.log, bot.log.2026-04-12, etc.

    Args:
        level: Logging level (default: logging.INFO)
    """
    # Get the project root directory (sbi-discord-bot folder)
    project_root = Path(__file__).parent.parent.parent

    # Ensure logs directory exists in project root
    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)

    log_format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"

    file_handler = TimedRotatingFileHandler(
        logs_dir / "bot.log",
        when="midnight",
        backupCount=0,
    )
    file_handler.setFormatter(logging.Formatter(log_format))

    # Configure logging
    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[
            file_handler,
            logging.StreamHandler(),
        ],
        force=True,  # Override any existing configuration
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for the given name.

    Args:
        name: Usually __name__ from the calling module

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


# Initialize logging configuration when module is imported
setup_logging()
