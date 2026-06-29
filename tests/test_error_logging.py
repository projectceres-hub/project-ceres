import logging
import unittest
from unittest import mock

import core.errors as errors


class ErrorLoggingTests(unittest.TestCase):
    def test_setup_logger_survives_unwritable_log_file(self) -> None:
        logger = logging.getLogger("project_ceres.errors")
        old_handlers = list(logger.handlers)
        for handler in old_handlers:
            logger.removeHandler(handler)

        try:
            with mock.patch(
                "core.errors.RotatingFileHandler",
                side_effect=PermissionError("denied"),
            ):
                configured = errors._setup_logger()

            self.assertIs(configured, logger)
            self.assertTrue(configured.handlers)
        finally:
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
            for handler in old_handlers:
                logger.addHandler(handler)


if __name__ == "__main__":
    unittest.main()
