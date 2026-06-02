import logging
from logging.handlers import RotatingFileHandler

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        RotatingFileHandler(
            "app.log", maxBytes=2000000, backupCount=3
        ),  # Rotating file handler
        logging.StreamHandler(),  # Output to console
    ],
)

# Example logger usage in application
logger = logging.getLogger("ExampleLogger")


def example_function():
    try:
        logger.info("Example function started.")
        # Simulate work or computation
        result = 10 / 0  # This will cause a divide by zero exception
    except ZeroDivisionError as e:
        logger.error("An error occurred: %s", e, exc_info=True)
    else:
        logger.info("Example function succeeded with result: %d", result)


# Run example
if __name__ == "__main__":
    logger.info("Application started.")
    example_function()
    logger.info("Application finished.")
