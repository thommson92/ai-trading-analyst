import logging

from ibkrspike.logging_setup import configure_logging


def test_configure_logging_unterdrueckt_ib_async_wrapper_info_logs() -> None:
    logging.getLogger("ib_async.wrapper").setLevel(logging.INFO)

    configure_logging()

    assert logging.getLogger("ib_async.wrapper").getEffectiveLevel() == logging.WARNING


def test_configure_logging_belaesst_eigene_logger_auf_info() -> None:
    configure_logging()

    assert logging.getLogger("ibkrspike.cli").getEffectiveLevel() == logging.INFO
