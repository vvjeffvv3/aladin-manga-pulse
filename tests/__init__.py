"""프로젝트 unittest 실행 결과를 요약해서 출력한다."""

from __future__ import annotations

import pkgutil
import sys
import unittest
from pathlib import Path


class ReportingTestSuite(unittest.TestSuite):
    """파일별 테스트 설명과 프로젝트용 결과 요약을 출력한다."""

    def run(
        self,
        result: unittest.TestResult,
        debug: bool = False,
    ) -> unittest.TestResult:
        original_start_test = result.startTest
        original_add_success = result.addSuccess
        original_add_failure = result.addFailure
        original_add_error = result.addError
        original_show_all = getattr(result, "showAll", None)
        original_dots = getattr(result, "dots", None)
        current_file: str | None = None

        def test_file_name(test: unittest.TestCase) -> str:
            module = sys.modules.get(test.__class__.__module__)
            module_path = getattr(module, "__file__", None)
            return Path(module_path).name if module_path else "테스트 파일"

        def test_description(test: unittest.TestCase) -> str:
            description = test.shortDescription()
            return description.splitlines()[0] if description else str(test)

        def start_test(test: unittest.TestCase) -> None:
            nonlocal current_file
            file_name = test_file_name(test)
            if file_name != current_file:
                print(f"\n========={file_name}====================")
                current_file = file_name
            original_start_test(test)

        def add_success(test: unittest.TestCase) -> None:
            original_add_success(test)
            print(f"{test_description(test)} : 테스트 통과")

        def add_failure(test: unittest.TestCase, err) -> None:
            original_add_failure(test, err)
            print(f"{test_description(test)} : 테스트 실패")

        def add_error(test: unittest.TestCase, err) -> None:
            original_add_error(test, err)
            print(f"{test_description(test)} : 테스트 오류")

        # -v 옵션의 기본 개별 출력 대신 아래의 한국어 설명을 사용한다.
        result.startTest = start_test
        result.addSuccess = add_success
        result.addFailure = add_failure
        result.addError = add_error
        if original_show_all is not None:
            result.showAll = False
        if original_dots is not None:
            result.dots = False

        try:
            super().run(result, debug)
        finally:
            result.startTest = original_start_test
            result.addSuccess = original_add_success
            result.addFailure = original_add_failure
            result.addError = original_add_error
            if original_show_all is not None:
                result.showAll = original_show_all
            if original_dots is not None:
                result.dots = original_dots

        if result.wasSuccessful():
            print("\n==================================")
            print(
                f"[통과] 전체 테스트 통과: {result.testsRun}개 테스트를 "
                "모두 통과했습니다."
            )
        else:
            print("\n==================================")
            print(
                f"[실패] 전체 {result.testsRun}개 중 "
                f"{len(result.failures) + len(result.errors)}개 테스트를 "
                "확인해야 합니다."
            )

        return result


def load_tests(
    loader: unittest.TestLoader,
    standard_tests: unittest.TestSuite,
    pattern: str | None,
) -> ReportingTestSuite:
    """unittest discover가 사용하는 테스트 스위트를 결과 출력용으로 감싼다."""
    suite = ReportingTestSuite()

    # 프로젝트 루트에서 discover할 때 패키지 내부 테스트를 직접 등록한다.
    # 이렇게 해야 ReportingTestSuite가 전체 테스트를 한 번에 감쌀 수 있다.
    discovered_module_names = sorted(
        module_info.name
        for module_info in pkgutil.iter_modules(__path__)
        if module_info.name.startswith("test_")
    )
    preferred_order = (
        "test_scraper",
        "test_daily_snapshot",
        "test_gold_transform",
    )
    module_names = [
        module_name
        for module_name in preferred_order
        if module_name in discovered_module_names
    ]
    module_names.extend(
        module_name
        for module_name in discovered_module_names
        if module_name not in module_names
    )

    for module_name in module_names:
        suite.addTests(loader.loadTestsFromName(f"{__name__}.{module_name}"))

    # 표준 테스트 로더가 별도로 전달한 테스트가 있다면 누락하지 않는다.
    if not module_names:
        suite.addTests(standard_tests)

    return suite
