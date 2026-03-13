import time
import zipfile
import concurrent.futures
from io import BytesIO
from pathlib import Path

class MockRecord:
    def __init__(self, s3_key):
        self.s3_key = s3_key

class MockService:
    def download_buffer(self, s3_key):
        time.sleep(0.1) # Simulate network delay
        b = BytesIO(b"dummy data " * 1000)
        b.seek(0)
        return b

def baseline(records, service):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for record in records:
            file_buffer = service.download_buffer(record.s3_key)
            zipf.writestr(Path(record.s3_key).name, file_buffer.getvalue())
    zip_buffer.seek(0)
    return zip_buffer

def optimized(records, service):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_record = {
                executor.submit(service.download_buffer, record.s3_key): record
                for record in records
            }
            for future in concurrent.futures.as_completed(future_to_record):
                record = future_to_record[future]
                file_buffer = future.result()
                zipf.writestr(Path(record.s3_key).name, file_buffer.getvalue())
    zip_buffer.seek(0)
    return zip_buffer

def main():
    service = MockService()
    records = [MockRecord(f"epubs/book_{i}.epub") for i in range(20)]

    print("Running baseline...")
    start = time.time()
    b_buf = baseline(records, service)
    t_base = time.time() - start
    print(f"Baseline: {t_base:.2f}s")

    print("Running optimized...")
    start = time.time()
    o_buf = optimized(records, service)
    t_opt = time.time() - start
    print(f"Optimized: {t_opt:.2f}s")

    print(f"Improvement: {t_base / t_opt:.2f}x faster")

if __name__ == "__main__":
    main()
