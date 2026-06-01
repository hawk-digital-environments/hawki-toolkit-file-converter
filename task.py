from pathlib import Path

from prefect import flow, serve

from utils.processor import process_file_core


@flow(log_prints=True)
async def run_process_file(
    file_path: str, filename: str, result_dir: str
) -> dict:
    file_bytes = Path(file_path).read_bytes()
    zip_bytes, headers = await process_file_core(file_bytes, filename)
    Path(result_dir).mkdir(parents=True, exist_ok=True)
    result_path = Path(result_dir) / "output.zip"
    result_path.write_bytes(zip_bytes)
    return {"result_path": str(result_path), "headers": headers}


if __name__ == "__main__":
    deploy = run_process_file.to_deployment(name="process-file")
    serve(deploy)
