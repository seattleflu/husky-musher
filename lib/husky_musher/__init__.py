import logging
from pythonjsonlogger import jsonlogger
from id3c.logging.config import load_config


def configure_logger(filename):
    logger = logging.getLogger()
    with open(filename, "rb") as file:
        logging.config.dictConfig(load_config(file))
