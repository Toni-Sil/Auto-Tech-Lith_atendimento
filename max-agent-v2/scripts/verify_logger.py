from app.utils.logger import get_logger

logger = get_logger("test_logger")

if __name__ == "__main__":
    logger.info("Info level log check")
    logger.debug("Debug level log check (should verify against settings.DEBUG/LOG_LEVEL)")
    logger.warning("Warning level log check")
    print("Logger verification script finished.")
