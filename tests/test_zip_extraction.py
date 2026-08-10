import os
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.manager import DownloadManager
from core.models import DownloadTask, DownloadType


def test_zip_extraction():
    # We will test the extract_zip logic directly by calling the internal function,
    # or by copying the logic if we just want to verify it independently,
    # but the prompt says: "Run the extraction function on both"
    # The extraction function is an inner function inside _on_task_status_changed.
    # We can just extract it or recreate it for the test.
    # Actually, the instructions say to run the extraction function.
    # We can let DownloadManager trigger it or just duplicate the exact logic to test it.
    # Let's trigger it via DownloadManager by completing a task.

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create fixtures
        single_root_zip = os.path.join(tmpdir, "single_root.zip")
        multi_root_zip = os.path.join(tmpdir, "multi_root.zip")

        # 1. Zip with single top-level folder
        with zipfile.ZipFile(single_root_zip, "w") as zf:
            zf.writestr("single_root_folder/file1.txt", "hello")
            zf.writestr("single_root_folder/subfolder/file2.txt", "world")

        # 2. Zip with multiple top-level items
        with zipfile.ZipFile(multi_root_zip, "w") as zf:
            zf.writestr("file1.txt", "hello")
            zf.writestr("folder1/file2.txt", "world")

        dm = DownloadManager(tmpdir)
        dm.set_config({"auto_extract": True})

        # Test 1: Single root
        t1 = DownloadTask(
            source="dummy", dest_path=single_root_zip, type=DownloadType.HTTP
        )
        t1.status = DownloadStatus.COMPLETED
        dm._on_task_status_changed(t1)

        # Test 2: Multi root
        t2 = DownloadTask(
            source="dummy", dest_path=multi_root_zip, type=DownloadType.HTTP
        )
        t2.status = DownloadStatus.COMPLETED
        dm._on_task_status_changed(t2)

        # Wait for background extraction threads to finish
        time.sleep(1.0)

        # Verify 1
        single_extract_dir = os.path.splitext(single_root_zip)[0]  # tmpdir/single_root
        assert os.path.exists(single_extract_dir)
        # We expect file1.txt and subfolder to be directly inside single_extract_dir, not inside another single_root_folder
        items = set(os.listdir(single_extract_dir))
        assert "file1.txt" in items
        assert "subfolder" in items
        assert "single_root_folder" not in items

        # Verify 2
        multi_extract_dir = os.path.splitext(multi_root_zip)[0]  # tmpdir/multi_root
        assert os.path.exists(multi_extract_dir)
        items = set(os.listdir(multi_extract_dir))
        assert "file1.txt" in items
        assert "folder1" in items

        print("test_zip_extraction passed")


if __name__ == "__main__":
    from core.models import DownloadStatus

    test_zip_extraction()
