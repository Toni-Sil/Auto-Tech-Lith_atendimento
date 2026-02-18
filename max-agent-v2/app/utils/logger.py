"""
Logger centralizado
Antigravity Skill: error-handling-patterns
"""
import logging
import sys
from app.config.settings import get_settings

def get_logger(name: str) -> logging.Logger:
    """
    Cria logger configurado
    
    Args:
        name: Nome do logger (geralmente __name__)
        
    Returns:
        logging.Logger: Logger configurado
    """
    settings = get_settings()
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.log_level))
    
    # Handler console
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, settings.log_level))
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger
