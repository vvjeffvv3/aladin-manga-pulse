import unittest
from pathlib import Path


class DailyPipelineContractTests(unittest.TestCase):
    """Windows 배치 파이프라인의 단계 순서와 실패 계약을 검증한다."""

    @classmethod
    def setUpClass(cls):
        pipeline_path = Path(__file__).resolve().parents[1] / "run_daily_pipeline.bat"
        cls.pipeline_text = pipeline_path.read_text(encoding="utf-8-sig")

    def test_batch_runs_crawl_gold_and_mysql_in_order(self):
        """배치 파일이 크롤링·Gold 변환·MySQL 적재를 순서대로 실행"""
        markers = (
            "aladin_manga_scraper.py",
            "gold_transform.py",
            "mysql_loader.py",
        )
        positions = [self.pipeline_text.index(marker) for marker in markers]

        self.assertEqual(positions, sorted(positions))
        for marker in markers:
            self.assertIn(
                f'"%PYTHON%" -u "%PROJECT_DIR%{marker}"',
                self.pipeline_text,
            )

    def test_batch_logs_lifecycle_and_routes_step_errors_to_failed(self):
        """배치 파일이 단계별 로그와 성공·실패 종료 상태를 기록"""
        self.assertIn('set "PROJECT_DIR=%~dp0"', self.pipeline_text)
        self.assertIn('set "LOG_FILE=%LOG_DIR%\\daily_pipeline.log"', self.pipeline_text)
        self.assertIn("CRAWL START", self.pipeline_text)
        self.assertIn("GOLD START", self.pipeline_text)
        self.assertIn("MYSQL START", self.pipeline_text)
        self.assertIn("echo [%date% %time%] SUCCESS", self.pipeline_text)
        self.assertIn("if errorlevel 1 goto failed", self.pipeline_text)
        self.assertIn("goto failed", self.pipeline_text)
        self.assertIn("FAILED (exit=%EXIT_CODE%)", self.pipeline_text)


if __name__ == "__main__":
    unittest.main()
