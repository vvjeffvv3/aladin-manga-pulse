"""Django 테스트 결과를 파일별 설명과 함께 출력하는 테스트 러너."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from django.test.runner import DiscoverRunner


class DashboardTestResult(unittest.TextTestResult):
    """각 테스트의 한국어 설명과 통과 여부를 출력한다."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.showAll = False
        self.dots = False
        self._current_file: str | None = None

    @staticmethod
    def _file_name(test: unittest.TestCase) -> str:
        module = sys.modules.get(test.__class__.__module__)
        module_path = getattr(module, "__file__", None)
        return Path(module_path).name if module_path else "테스트 파일"

    @staticmethod
    def _description(test: unittest.TestCase) -> str:
        description = test.shortDescription()
        return description.splitlines()[0] if description else str(test)

    def startTest(self, test: unittest.TestCase) -> None:
        file_name = self._file_name(test)
        if file_name != self._current_file:
            self.stream.write(f"\n========={file_name}====================\n")
            self._current_file = file_name
            self.stream.flush()
        super().startTest(test)

    def addSuccess(self, test: unittest.TestCase) -> None:
        super().addSuccess(test)
        self.stream.write(f"{self._description(test)} : 테스트 통과\n")
        self.stream.flush()

    def addFailure(self, test: unittest.TestCase, err) -> None:
        super().addFailure(test, err)
        self.stream.write(f"{self._description(test)} : 테스트 실패\n")
        self.stream.flush()

    def addError(self, test: unittest.TestCase, err) -> None:
        super().addError(test, err)
        self.stream.write(f"{self._description(test)} : 테스트 오류\n")
        self.stream.flush()

    def addSkip(self, test: unittest.TestCase, reason: str) -> None:
        super().addSkip(test, reason)
        self.stream.write(f"{self._description(test)} : 테스트 건너뜀\n")
        self.stream.flush()


class DashboardTestRunner(unittest.TextTestRunner):
    """기본 unittest 결과 뒤에 전체 테스트 요약을 추가한다."""

    resultclass = DashboardTestResult

    def run(self, test):
        result = super().run(test)
        self.stream.write("\n==================================\n")
        if result.wasSuccessful():
            self.stream.write(
                f"[통과] 전체 테스트 통과: {result.testsRun}개 테스트를 "
                "모두 통과했습니다.\n"
            )
        else:
            self.stream.write(
                f"[실패] 전체 {result.testsRun}개 중 "
                f"{len(result.failures) + len(result.errors)}개 테스트를 "
                "확인해야 합니다.\n"
            )
        self.stream.flush()
        return result


class DashboardDiscoverRunner(DiscoverRunner):
    """dashboard 테스트에 사용자 정의 결과 출력기를 연결한다."""

    test_runner = DashboardTestRunner

    def get_resultclass(self):
        return DashboardTestResult
