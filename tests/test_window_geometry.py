import unittest

from PyQt5.QtCore import QRect

from ui.main_window import _rect_intersects_any_screen


class WindowGeometryTests(unittest.TestCase):
    def test_rect_intersects_available_screen(self) -> None:
        screens = [QRect(0, 0, 1920, 1040)]

        self.assertTrue(_rect_intersects_any_screen(QRect(260, 90, 1400, 860), screens))

    def test_rect_outside_available_screens_is_rejected(self) -> None:
        screens = [QRect(0, 0, 1920, 1040)]

        self.assertFalse(_rect_intersects_any_screen(QRect(5000, 5000, 1400, 860), screens))

    def test_empty_rect_is_rejected(self) -> None:
        screens = [QRect(0, 0, 1920, 1040)]

        self.assertFalse(_rect_intersects_any_screen(QRect(0, 0, 0, 0), screens))


if __name__ == "__main__":
    unittest.main()
