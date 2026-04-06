import logging
from pathlib import Path


def setup_logger(name: str = "amil_bot",
                 log_file: str | Path | None = None,
                 level: int = logging.INFO) -> logging.Logger:
    """
    Cria um logger com saída no console e (opcional) em arquivo.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Evita adicionar handlers duplicados
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Arquivo (opcional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger